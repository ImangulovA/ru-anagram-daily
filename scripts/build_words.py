#!/usr/bin/env python3
"""
build_words.py — RU word/clue builder for "Анаграмма дня" (ru-anagram-daily).

Produces data/words_defs.json: an object keyed by UPPERCASE Cyrillic word ->
{ "def": <primary crossword clue>, "clues": [<clue>, ...], "freq": <0..1> }.

Sourcing method (open crossword-helper source, so clues are correct):
  * WORDS + FREQUENCY: the `wordfreq` package (Zipf scale, Russian corpora)
    supplies candidate surface forms (top-N by frequency) and the frequency used
    for difficulty/curation. Zipf ~[0,8]: ~1 rare, ~7+ very common.
  * CLUES (definitions): the crossword-helper "Словарь кроссвордиста" at
    graycell.ru. Page graycell.ru/word/<слово> lists the crossword clues for
    which the word is the answer, e.g. КОШКА -> "Ласковый хищник". These are
    authored crossword definitions, so they are correct (per project decision to
    take them verbatim; length is not constrained). A word is KEPT only if
    graycell has at least one clue for it, which also filters the pool down to
    real crossword answer words (overwhelmingly nouns) -- ideal for anagrams.

We store up to MAX_CLUES cleaned clues per word so a later agent pass can pick
the clearest clue for the ~few hundred words that actually appear in puzzles.
The provisional "def" is the plainest-looking clue (see rank_clue).

Frequency normalization:
  freq = clamp((zipf - ZIPF_MIN) / (ZIPF_MAX - ZIPF_MIN), 0, 1)
  ZIPF_MIN = 1.5, ZIPF_MAX = 7.0. Candidates below MIN_ZIPF_KEEP are never
  fetched.

Network politeness / re-runnability:
  Fetches go through a bounded ThreadPool with a persistent on-disk cache
  (data/graycell_cache.json). Re-runs reuse the cache and only fetch new words.
  Output is deterministic (sorted keys) -> idempotent.

Usage (run inside the anagram-daily venv, which has wordfreq):
  ~/Desktop/anagram-daily/.venv/bin/python scripts/build_words.py --limit 25000
  ~/Desktop/anagram-daily/.venv/bin/python scripts/build_words.py --verify
"""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
import threading
import time
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MIN_LEN = 2
MAX_LEN = 15

ZIPF_MIN = 1.5
ZIPF_MAX = 7.0
MIN_ZIPF_KEEP = 2.3     # skip (never fetch) candidates rarer than this

MAX_CLUES = 12          # how many clues to retain per word
MAX_CLUE_LEN = 200      # drop absurdly long clue strings

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA_DIR = os.path.join(ROOT, "data")
OUT_PATH = os.path.join(DATA_DIR, "words_defs.json")
CACHE_PATH = os.path.join(DATA_DIR, "graycell_cache.json")

# Russian alphabet; Ё is its OWN letter (strict, per project decision).
RU_RE = re.compile(r"^[а-яё]+$")

WORD_URL = "https://graycell.ru/word/"
USER_AGENT = ("ru-anagram-daily/1.0 (personal daily word game; "
              "https://github.com/ImangulovA)")

# Offensive / clearly inappropriate terms to exclude (kept small, explicit).
BLOCKLIST = {
    "хуй", "пизда", "блядь", "блять", "ебать", "сука", "мудак", "гондон",
    "пидор", "пидорас", "залупа", "хер", "жопа", "говно", "срать", "ссать",
    "долбоёб", "выблядок", "манда", "елда", "хохол", "жид", "чурка",
}

# Each crossword clue lives in <p class="description">...</p> with a leading
# "<b>N.</b>" answer-index marker.
_DESC_RE = re.compile(r'<p class="description">(.*?)</p>', re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_NUM_RE = re.compile(r"^\s*\d+[.)]\s*")

_SSL = ssl.create_default_context()


# ---------------------------------------------------------------------------
# Fetch + parse
# ---------------------------------------------------------------------------
def fetch_clues(word: str, retries: int = 2) -> list[str] | None:
    """Return the list of cleaned crossword clues for a word (possibly empty),
    or None on a hard network failure (so the caller does NOT cache it)."""
    url = WORD_URL + urllib.parse.quote(word)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=25, context=_SSL) as r:
                html = r.read().decode(
                    r.headers.get_content_charset() or "utf-8", "replace")
            return parse_clues(html)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return []                    # no such answer word: cache empty
            last = exc
        except Exception as exc:
            last = exc
        time.sleep(0.4 * (attempt + 1))
    print(f"[fetch] give up on {word!r}: {last}", file=sys.stderr)
    return None


def parse_clues(html: str) -> list[str]:
    body = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", "",
                  html, flags=re.S)
    out: list[str] = []
    seen = set()
    for frag in _DESC_RE.findall(body):
        t = _TAG_RE.sub(" ", frag)
        t = t.replace("&nbsp;", " ").replace("&laquo;", "«").replace(
            "&raquo;", "»").replace("&mdash;", "—").replace("&ndash;", "–")
        t = re.sub(r"\s+", " ", t).strip()
        t = _NUM_RE.sub("", t)               # drop leading "1." marker
        t = re.sub(r"\s+([.,!?»])", r"\1", t)   # tidy space before punctuation
        t = re.sub(r"(«)\s+", r"\1", t)
        t = t.strip()
        if not t or len(t) > MAX_CLUE_LEN:
            continue
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


# ---------------------------------------------------------------------------
# Clue quality ranking (pick the plainest, most definition-like clue)
# ---------------------------------------------------------------------------
def _norm(s: str) -> str:
    return re.sub(r"[^а-яё]", "", s.lower())


def is_circular(word: str, clue: str) -> bool:
    """True if the clue restates the answer (contains the word or a long stem)."""
    w = word.lower()
    cl = clue.lower()
    if w in cl:
        return True
    if len(w) >= 5 and w[:5] in cl:          # rough shared-stem guard
        return True
    return False


def rank_clue(word: str, clue: str) -> tuple:
    """Sort key (lower is better) preferring plain, definition-like clues.

    Penalizes riddle-questions, quoted wordplay, letter-count riddles, and very
    short/very long clues. Used to choose the provisional primary "def"; the
    later agent pass makes the final per-puzzle choice among all clues.
    """
    cl = clue.lower()
    penalty = 0
    if "?" in clue:
        penalty += 4                          # riddle question
    if "«" in clue or "»" in clue or '"' in clue:
        penalty += 2                          # quoted wordplay
    if re.search(r"букв|буквами|пятью|четырьмя|наоборот|анаграмм", cl):
        penalty += 5                          # letter/spelling wordplay
    if clue.strip().startswith(("«", "-", "—", "...")):
        penalty += 2
    n = len(clue)
    if n < 12:
        penalty += 2                          # too terse to be a clear clue
    length_score = abs(n - 45)                # sweet spot ~45 chars
    return (penalty, length_score, clue)


def choose_clues(word: str, clues: list[str]) -> list[str]:
    """Drop circular clues, rank by plainness, keep the best MAX_CLUES."""
    good = [c for c in clues if not is_circular(word, c)]
    good.sort(key=lambda c: rank_clue(word, c))
    return good[:MAX_CLUES]


# ---------------------------------------------------------------------------
# Frequency
# ---------------------------------------------------------------------------
def normalize_zipf(zipf: float) -> float:
    if zipf <= 0:
        return 0.0
    val = (zipf - ZIPF_MIN) / (ZIPF_MAX - ZIPF_MIN)
    return round(max(0.0, min(1.0, val)), 4)


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
_cache_lock = threading.Lock()


def load_cache() -> dict:
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}
    return {}


def save_cache(cache: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False)
    os.replace(tmp, CACHE_PATH)


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
def gather_candidates(limit: int) -> list[str]:
    from wordfreq import top_n_list, zipf_frequency
    raw = top_n_list("ru", limit)
    out, seen = [], set()
    for w in raw:
        w = w.strip().lower()
        if not RU_RE.match(w):
            continue
        if not (MIN_LEN <= len(w) <= MAX_LEN):
            continue
        if w in BLOCKLIST or w in seen:
            continue
        if zipf_frequency(w, "ru") < MIN_ZIPF_KEEP:
            continue
        seen.add(w)
        out.append(w)
    return out


def build(limit: int, workers: int) -> dict:
    from wordfreq import zipf_frequency

    candidates = gather_candidates(limit)
    print(f"[build] wordfreq candidates after filter: {len(candidates)}",
          file=sys.stderr)

    cache = load_cache()
    todo = [w for w in candidates if w not in cache]
    print(f"[build] cached={len(candidates) - len(todo)} to_fetch={len(todo)}",
          file=sys.stderr)

    done = 0
    if todo:
        def work(word):
            return word, fetch_clues(word)

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(work, w) for w in todo]
            for fut in as_completed(futures):
                word, clues = fut.result()
                if clues is not None:            # cache empty [] too (real 404)
                    with _cache_lock:
                        cache[word] = clues
                done += 1
                if done % 500 == 0:
                    print(f"[build] fetched {done}/{len(todo)} "
                          f"(kept-so-far cache={len(cache)})", file=sys.stderr)
                    save_cache(cache)
        save_cache(cache)

    out: dict[str, dict] = {}
    drop_noclue = 0
    for word in candidates:
        raw_clues = cache.get(word)
        if not raw_clues:                        # None (unfetched) or [] (none)
            drop_noclue += 1
            continue
        clues = choose_clues(word, raw_clues)
        if not clues:                            # only circular clues existed
            drop_noclue += 1
            continue
        freq = normalize_zipf(zipf_frequency(word, "ru"))
        out[word.upper()] = {
            "def": clues[0],
            "clues": clues,
            "freq": freq,
        }

    print(f"[build] kept={len(out)} drop_no_clue={drop_noclue}", file=sys.stderr)
    return out


def write_json(data: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, sort_keys=True, indent=0,
                  separators=(",", ":"))
        fh.write("\n")


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------
def verify(path: str) -> None:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    total = len(data)
    lengths = Counter(len(w) for w in data)
    clue_counts = Counter(min(len(v.get("clues", [])), 12) for v in data.values())
    print("\n===== VERIFY words_defs.json =====")
    print(f"path:        {path}")
    print(f"total words: {total}")
    print(f"clue-count histogram (capped 12): {dict(sorted(clue_counts.items()))}")
    print("\nword-length histogram:")
    for length in sorted(lengths):
        bar = "#" * min(60, lengths[length] // 50 + 1)
        print(f"  {length:2d}: {lengths[length]:6d}  {bar}")
    ordered = sorted(data.items(), key=lambda kv: kv[1]["freq"], reverse=True)
    if ordered:
        picks = [ordered[0], ordered[len(ordered)//4], ordered[len(ordered)//2],
                 ordered[3*len(ordered)//4], ordered[-1]]
        print("\n5 samples (high -> low freq):")
        for w, v in picks:
            print(f"  {w} freq={v['freq']} def={v['def']!r}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Build RU words_defs.json (graycell).")
    ap.add_argument("--limit", type=int, default=25000,
                    help="how many top wordfreq tokens to consider")
    ap.add_argument("--workers", type=int, default=12,
                    help="parallel graycell fetch workers")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--out", default=OUT_PATH)
    args = ap.parse_args()

    if args.verify and os.path.exists(args.out):
        verify(args.out)
        return

    data = build(args.limit, args.workers)
    write_json(data, args.out)
    print(f"[build] wrote {len(data)} words -> {args.out}", file=sys.stderr)
    verify(args.out)


if __name__ == "__main__":
    main()
