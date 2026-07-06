#!/usr/bin/env python3
"""
Анаграмма дня -- anagram engine + daily puzzle generator (RU).

Consumes  data/words_defs.json  (build_words.py: WORD -> {def, clues, freq})
Emits     data/puzzles.json  and  data/puzzles.js  (window.PUZZLES = [...])
          and app/src/lib/game/data/days.js (the SvelteKit data module)

Core invariant for every puzzle:  sorted(A.word + B.word) == sorted(C.word)
Length rules: len(C) >= 8, len(A) >= 2, len(B) >= 2  (=> len(A)+len(B)==len(C))
Ё is a STRICT, distinct letter (no ё->е folding), per project decision, so the
multiset signature naturally keeps ё separate.

Algorithm (efficient, NOT O(n^2) over pairs):
  * signature(word) = "".join(sorted(word))  -- multiset key (Cyrillic).
  * anagram groups: signature -> [words]; plus a set of all signatures.
  * For each final word C (len>=9): enumerate sub-multisets of C's letters that
    are a known word signature (candidate A). Remainder = C minus A; if remainder
    is also a known signature and both halves have len >= 2, we have a valid split.

Reproducible: any randomness is seeded deterministically; a byte-identical
words_defs.json yields byte-identical puzzles.
"""

import itertools
import json
import os
import re
import sys
from collections import Counter
from datetime import date, timedelta

# ----------------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(ROOT, "data")
WORDS_DEFS_PATH = os.path.join(DATA_DIR, "words_defs.json")
PUZZLES_JSON_PATH = os.path.join(DATA_DIR, "puzzles.json")
PUZZLES_JS_PATH = os.path.join(DATA_DIR, "puzzles.js")
DAYS_JS_PATH = os.path.join(
    ROOT, "app", "src", "lib", "game", "data", "days.js")

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
ANCHOR_DATE = date(2026, 7, 6)   # day 0 (public launch anchor = today)
# First (earliest) buffer day index. Negative days are playable pre-launch days
# from early June. date(day) = ANCHOR_DATE + day. day -30 -> 2026-06-06.
FIRST_DAY = -30
LAST_DAY = 277                    # inclusive target; auto-trimmed from the tail
#                                  if the disjoint-word pool can't fill it.
NUM_DAYS = LAST_DAY - FIRST_DAY + 1

# Every word (A, B AND C) is used AT MOST ONCE across the whole buffer -- no
# word repeats at all in the first 300 days (per project decision). This makes
# MAX_SOURCE_WORD_USES / SOURCE_WORD_MIN_GAP moot (each word appears once).
UNIQUE_WORDS = True
MIN_C_LEN = 8
MIN_PART_LEN = 2
PREFERRED_C_LEN = (8, 11)
MIN_WORD_FREQ = 0.12
MIN_C_FREQ = 0.20
SEED = 20260706

# --- Curation-quality knobs -------------------------------------------------
LEN2_PENALTY = 0.55
PREFERRED_MIN_SRC_LEN = 3
MAX_SOURCE_WORD_USES = 3
SOURCE_WORD_MIN_GAP = 7

# --- Weekday difficulty ramp (by final-word LENGTH), per project decision ----
# weekday(): Mon=0 .. Sun=6.  Sun/Mon/Tue -> 8 | Wed/Thu -> 9 | Fri/Sat -> 10..12
# Aligned to the EN version so RU is not harder than English (RU words already
# run longer on average, so matching EN's letter counts keeps parity).
WEEKDAY_C_LENS = {
    6: (8,),             # Sunday
    0: (8,),             # Monday
    1: (8,),             # Tuesday
    2: (9,),             # Wednesday
    3: (9,),             # Thursday
    4: (10, 11, 12),     # Friday
    5: (10, 11, 12),     # Saturday
}

# Russian alphabet, Ё strict / distinct.
RU_RE = re.compile(r"^[А-ЯЁ]+$")


def len_target_for_weekday(weekday):
    return set(WEEKDAY_C_LENS.get(weekday, (9, 10, 11, 12, 13)))


def build_starter_defs():
    """No embedded RU starter dictionary; words_defs.json is required. Returns an
    empty dict so verify_puzzles' bootstrap path degrades gracefully."""
    return {}


# ----------------------------------------------------------------------------
# Loading / cleaning
# ----------------------------------------------------------------------------
def load_words_defs():
    if os.path.exists(WORDS_DEFS_PATH):
        with open(WORDS_DEFS_PATH, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        source = "data/words_defs.json"
    else:
        raw = build_starter_defs()
        source = "EMPTY (words_defs.json absent -- run build_words.py first)"

    clean = {}
    for word, meta in raw.items():
        if not isinstance(word, str):
            continue
        w = word.strip().upper()
        if not RU_RE.match(w):
            continue
        if w in BLOCKED_WORDS:            # cognate-magnet source words
            continue
        if not (2 <= len(w) <= 15):
            continue
        if not isinstance(meta, dict):
            continue
        definition = meta.get("def")
        if not isinstance(definition, str) or not definition.strip():
            continue
        try:
            freq = float(meta.get("freq", 0.0))
        except (TypeError, ValueError):
            freq = 0.0
        freq = max(0.0, min(1.0, freq))
        clean[w] = {"def": definition.strip(), "freq": freq}
    return clean, source


def signature(word):
    return "".join(sorted(word))


# ----------------------------------------------------------------------------
# Russian stemming (for circular-clue + cognate detection). Uses nltk's
# algorithmic Snowball Russian stemmer (offline, no downloads).
# ----------------------------------------------------------------------------
try:
    from nltk.stem.snowball import SnowballStemmer
    _STEMMER = SnowballStemmer("russian")

    def ru_stem(word):
        return _STEMMER.stem(word.lower())
except Exception:  # pragma: no cover -- fallback if nltk missing
    def ru_stem(word):
        return word.lower()


def is_circular_clue(word, clue):
    """True if the clue restates the answer (contains the word or its stem)."""
    if not clue:
        return True
    clue_l = clue.lower()
    w = word.lower()
    if w in clue_l:
        return True
    stem = ru_stem(word)
    if len(stem) >= 4 and stem in clue_l:
        return True
    return False


# ----------------------------------------------------------------------------
# Cognate / same-root detection (Russian)
# ----------------------------------------------------------------------------
def _common_prefix_len(x, y):
    n = min(len(x), len(y))
    i = 0
    while i < n and x[i] == y[i]:
        i += 1
    return i


def _longest_common_substring_len(x, y):
    """Length of the longest CONTIGUOUS shared substring (offline, small words)."""
    best = 0
    for i in range(len(x)):
        for j in range(len(y)):
            k = 0
            while (i + k < len(x) and j + k < len(y)
                   and x[i + k] == y[j + k]):
                k += 1
            if k > best:
                best = k
    return best


def are_cognate(w1, w2):
    """Heuristic: True if two Russian words share a root / are morphologically
    related. Deterministic and offline. Backed up by the agent audit for the
    irregular cases a stemmer misses.

    Signals:
      1. identical words;
      2. identical Snowball-Russian stems (e.g. СТОЛ / СТОЛЫ / СТОЛОВ);
      3. a long shared prefix (>= 5) -- same root family (ЛЕС-/ЛЕСН-);
      4. one word is a short extension of the other (shared >= 4, tail <= 2).
    """
    a, b = w1.lower(), w2.lower()
    if a == b:
        return True
    sa, sb = ru_stem(a), ru_stem(b)
    if sa == sb and min(len(sa), len(sb)) >= 3:
        return True
    cp = _common_prefix_len(a, b)
    if cp >= 5:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    if len(short) >= 4 and long_.startswith(short) and len(long_) - len(short) <= 2:
        return True
    # stems where one is a prefix of the other with a solid shared root
    if min(len(sa), len(sb)) >= 4 and (sa.startswith(sb) or sb.startswith(sa)) \
            and cp >= 4:
        return True
    # A long shared CONTIGUOUS chunk almost always means a shared root even when
    # it sits mid-word (РАБОТА/ОБРАБОТКА -> "работ", ФОРМАТ/ПЛАТФОРМА -> "форма").
    # >= 5 is safe: coincidental 5-letter overlaps between unrelated RU words are
    # rare. Catches the mid-word roots that stem/prefix checks miss.
    if _longest_common_substring_len(a, b) >= 5:
        return True
    return False


def triple_has_cognates(a_word, b_word, c_word):
    return (are_cognate(a_word, b_word)
            or are_cognate(a_word, c_word)
            or are_cognate(b_word, c_word))


def source_is_substring_of_final(a_word, b_word, c_word):
    cu = c_word.upper()
    return a_word.upper() in cu or b_word.upper() in cu


def _triple_key(a_word, b_word, c_word):
    return frozenset((a_word.upper(), b_word.upper(), c_word.upper()))


# Specific TRIPLES to exclude, populated from the semantic (AI) audit of same-
# root / etymologically-related answers the mechanical checks can't catch. We
# block the exact (A, B, C) combination -- NOT the answer word -- so a word can
# still appear via a different, clean anagram split.
#
# Found by the 6-way parallel cognate audit (2026-07-06): pairs the Snowball
# stemmer missed due to differing prefixes, consonant alternation (вод/вед,
# д/жд), or the shared root sitting mid-word (форм-).
_AUDIT_COGNATE_TRIPLES = [
    ("БОК", "РАБОТА", "ОБРАБОТКА"),      # работ-
    ("СВЕТ", "ДОВОЛЬНО", "НЕДОВОЛЬСТВО"),  # доволь-
    ("ИЕН", "ПЕРЕВОД", "ПРОВЕДЕНИЕ"),    # вод/вед
    ("ДЕН", "ПРАВА", "НЕПРАВДА"),        # прав-
    ("ПОЛЕ", "СТУПЕНИ", "ПОСТУПЛЕНИЕ"),  # ступ-
    ("СТАНОК", "ВАУ", "УСТАНОВКА"),      # станов-
    ("ФОРМАТ", "ПАЛ", "ПЛАТФОРМА"),      # форм-
    ("ЛЕДИ", "ВЕСТЬ", "СВИДЕТЕЛЬ"),      # вед- (этимологический)
    ("ЖИВОЕ", "ПАРНИ", "ПРОЖИВАНИЕ"),    # жив-
    ("НОЖИ", "ПЕРЕХОД", "ПРОХОЖДЕНИЕ"),  # ход/хожд
    # Round 2: surfaced after round-1 blocks were removed (delta re-audit).
    ("ИЕН", "СОСТАВ", "ВОССТАНИЕ"),      # ста-/став-
    ("СТУПЕНИ", "ЛЕВ", "ВСТУПЛЕНИЕ"),    # ступ-
    ("ДЕН", "ГАРАЖ", "ГРАЖДАНЕ"),        # не однокоренные, но костяк ГРАЖ- -> тривиально
    ("ЖАН", "НАСЛЕДИЕ", "НАСЛАЖДЕНИЕ"),  # разные корни, но визуально почти идентичны
]
BLOCKED_TRIPLES = {_triple_key(a, b, c) for a, b, c in _AUDIT_COGNATE_TRIPLES}

# Whole words removed from the pool: "cognate-magnet" sources that keep pairing
# with same-root answers (e.g. СТУПЕНИ -> ВСТУПЛЕНИЕ/НАСТУПЛЕНИЕ/ПОСТУПЛЕНИЕ,
# ступ- family). Cheaper than blocking each surfaced triple one by one.
BLOCKED_WORDS = {"СТУПЕНИ"}


# ----------------------------------------------------------------------------
# Anagram engine
# ----------------------------------------------------------------------------
def build_index(defs):
    groups = {}
    for word, meta in defs.items():
        sig = signature(word)
        groups.setdefault(sig, []).append(word)
    for sig, words in groups.items():
        words.sort(key=lambda w: (-defs[w]["freq"], w))
    return groups


def sub_multiset_signatures(counter):
    letters = sorted(counter.keys())
    ranges = [range(counter[ch] + 1) for ch in letters]
    for combo in itertools.product(*ranges):
        if sum(combo) == 0:
            continue
        yield "".join(ch * cnt for ch, cnt in zip(letters, combo) if cnt)


def _pick_word(candidates, defs, exclude=None):
    for w in candidates:
        if w != exclude:
            return w
    return None


def find_splits(defs, groups):
    all_sigs = set(groups.keys())
    triples = []
    seen_letter_splits = set()

    for c_word, c_meta in defs.items():
        clen = len(c_word)
        if clen < MIN_C_LEN:
            continue
        if c_meta["freq"] < MIN_C_FREQ:
            continue
        if is_circular_clue(c_word, c_meta["def"]):
            continue
        c_counter = Counter(c_word)

        for a_sig in sub_multiset_signatures(c_counter):
            a_len = len(a_sig)
            if a_len < MIN_PART_LEN or a_len > clen - MIN_PART_LEN:
                continue
            if a_sig not in all_sigs:
                continue
            rem = c_counter - Counter(a_sig)
            b_sig = "".join(sorted(rem.elements()))
            if len(b_sig) < MIN_PART_LEN:
                continue
            if b_sig not in all_sigs:
                continue
            key_pair = tuple(sorted((a_sig, b_sig)))
            dedupe_key = (c_word, key_pair)
            if dedupe_key in seen_letter_splits:
                continue
            seen_letter_splits.add(dedupe_key)

            a_word = _pick_word(groups[a_sig], defs, exclude=c_word)
            b_word = _pick_word(groups[b_sig], defs, exclude=c_word)
            if a_word is None or b_word is None:
                continue
            if a_word == b_word and a_sig == b_sig:
                alt = [w for w in groups[b_sig] if w != a_word]
                if not alt:
                    continue
                b_word = alt[0]

            a_freq = defs[a_word]["freq"]
            b_freq = defs[b_word]["freq"]
            if a_freq < MIN_WORD_FREQ or b_freq < MIN_WORD_FREQ:
                continue

            if is_circular_clue(a_word, defs[a_word]["def"]) or \
                    is_circular_clue(b_word, defs[b_word]["def"]):
                continue

            if triple_has_cognates(a_word, b_word, c_word):
                continue

            if source_is_substring_of_final(a_word, b_word, c_word):
                continue

            if _triple_key(a_word, b_word, c_word) in BLOCKED_TRIPLES:
                continue

            c_freq = c_meta["freq"]
            quality = _quality(clen, a_freq, b_freq, c_freq,
                               len(a_word), len(b_word))
            triples.append({
                "a": a_word, "b": b_word, "c": c_word,
                "a_freq": a_freq, "b_freq": b_freq, "c_freq": c_freq,
                "clen": clen, "quality": quality,
                "difficulty": _difficulty(clen, a_freq, b_freq, c_freq),
            })
    return triples


def _quality(clen, a_freq, b_freq, c_freq, a_len=3, b_len=3):
    freq_score = (a_freq + b_freq + 1.5 * c_freq)
    lo, hi = PREFERRED_C_LEN
    if lo <= clen <= hi:
        len_bonus = 1.0
    else:
        len_bonus = max(0.0, 1.0 - 0.15 * min(abs(clen - lo), abs(clen - hi)))
    quality = freq_score * (0.5 + 0.5 * len_bonus)
    for slen in (a_len, b_len):
        if slen < PREFERRED_MIN_SRC_LEN:
            quality *= LEN2_PENALTY
    return quality


def _raw_hardness(clen, a_freq, b_freq, c_freq):
    """Higher = harder. Rarer + longer => harder. C length normalized over the
    RU 9..13 window."""
    min_src = min(a_freq, b_freq)
    avg_freq = (a_freq + b_freq + c_freq) / 3.0
    rarity = 1.0 - (0.6 * min_src + 0.4 * avg_freq)
    length = min(1.0, max(0.0, (clen - 8) / 5.0))
    return 0.7 * rarity + 0.3 * length


def _difficulty(clen, a_freq, b_freq, c_freq):
    score = _raw_hardness(clen, a_freq, b_freq, c_freq)
    return max(1, min(5, int(round(1 + score * 4))))


# ----------------------------------------------------------------------------
# Curation into a contiguous daily buffer
# ----------------------------------------------------------------------------
def curate(triples, num_days):
    # Dedupe to distinct (C, {A,B}) splits, best quality first. We keep ALL such
    # splits (not just best-per-C) so the disjoint assigner has alternatives when
    # a word is already spent elsewhere.
    seen = set()
    uniq = []
    for t in sorted(triples, key=lambda t: (-t["quality"], t["c"])):
        key = (t["c"], frozenset((t["a"], t["b"])))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(t)

    selected = _place_days_unique(uniq)
    _assign_relative_difficulty(selected)
    return selected


def _assign_relative_difficulty(pool):
    ranked = sorted(
        pool,
        key=lambda t: (_raw_hardness(t["clen"], t["a_freq"], t["b_freq"],
                                     t["c_freq"]), t["c"]),
    )
    n = len(ranked)
    for rank, t in enumerate(ranked):
        q = min(4, (rank * 5) // n) if n else 0
        t["difficulty"] = q + 1


def _try_assign(order, days):
    """Try to assign a word-disjoint triple to every day in `days` (respecting
    weekday length targets). Returns {day: triple} on success, or None if any
    length bucket runs out of disjoint triples. Deterministic."""
    from collections import defaultdict

    day_lens = {d: len_target_for_weekday((ANCHOR_DATE + timedelta(days=d)).weekday())
                for d in days}
    used = set()          # every word (A, B, C) consumed so far
    assign = {}

    def fresh(t):
        w = {t["a"], t["b"], t["c"]}
        return len(w) == 3 and not (used & w)

    def take(t):
        used.update((t["a"], t["b"], t["c"]))

    # Day 0 (launch): reserve the friendliest common-word triple in its length set.
    if days and days[0] <= 0 <= days[-1]:
        day0_lens = day_lens[0]
        cands = [t for t in order
                 if t["clen"] in day0_lens
                 and len(t["a"]) >= PREFERRED_MIN_SRC_LEN
                 and len(t["b"]) >= PREFERRED_MIN_SRC_LEN
                 and min(t["a_freq"], t["b_freq"]) >= 0.30
                 and t["c_freq"] >= 0.40]
        cands.sort(key=lambda t: (-(t["a_freq"] + t["b_freq"] + t["c_freq"]), t["c"]))
        if cands:
            take(cands[0])
            assign[0] = cands[0]

    # Group remaining days by their length-set "bucket" and fill the scarcest
    # (lowest supply-per-day) bucket first so tight lengths never get starved.
    days_by_bucket = defaultdict(list)
    for d in days:
        if d in assign:
            continue
        days_by_bucket[frozenset(day_lens[d])].append(d)

    def supply(bucket):
        return sum(1 for t in order if t["clen"] in bucket)

    buckets = sorted(days_by_bucket,
                     key=lambda b: supply(b) / max(1, len(days_by_bucket[b])))

    for bucket in buckets:
        need_days = days_by_bucket[bucket]
        picks = []
        for t in order:
            if len(picks) >= len(need_days):
                break
            if t["clen"] in bucket and fresh(t):
                take(t)
                picks.append(t)
        if len(picks) < len(need_days):
            return None
        for d, t in zip(need_days, picks):
            assign[d] = t

    return assign


def _place_days_unique(uniq):
    """Assign a word-disjoint triple to every buffer day, trimming the tail
    (latest days) if the disjoint-word pool can't reach LAST_DAY. Prints how
    many days were actually placed."""
    if not uniq:
        raise RuntimeError("No valid triples were found; cannot build puzzles.")

    order = uniq  # already sorted by (-quality, c)
    last = LAST_DAY
    while last >= FIRST_DAY:
        assign = _try_assign(order, list(range(FIRST_DAY, last + 1)))
        if assign is not None:
            if last < LAST_DAY:
                print(f"[gen] pool exhausted past day {last}: trimmed tail "
                      f"{last + 1}..{LAST_DAY} ({LAST_DAY - last} days).",
                      file=sys.stderr)
            return [assign[d] for d in range(FIRST_DAY, last + 1)]
        last -= 1

    raise RuntimeError("No word-disjoint assignment possible for any range.")


def build_puzzles(defs, selected):
    puzzles = []
    for offset, t in enumerate(selected):
        day = FIRST_DAY + offset
        d = ANCHOR_DATE + timedelta(days=day)
        puzzles.append({
            "day": day,
            "date": d.isoformat(),
            "a": {"word": t["a"], "clue": defs[t["a"]]["def"]},
            "b": {"word": t["b"], "clue": defs[t["b"]]["def"]},
            "c": {"word": t["c"], "clue": defs[t["c"]]["def"]},
            "difficulty": t["difficulty"],
        })
    return puzzles


# ----------------------------------------------------------------------------
# Output
# ----------------------------------------------------------------------------
def write_outputs(puzzles):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PUZZLES_JSON_PATH, "w", encoding="utf-8") as fh:
        json.dump(puzzles, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    array_json = json.dumps(puzzles, ensure_ascii=False, indent=2)
    with open(PUZZLES_JS_PATH, "w", encoding="utf-8") as fh:
        fh.write("window.PUZZLES = " + array_json + ";\n")
    _write_days_js(puzzles)


def _write_days_js(puzzles):
    slim = [
        {
            "day": p["day"], "date": p["date"], "difficulty": p["difficulty"],
            "a": {"word": p["a"]["word"], "clue": p["a"]["clue"]},
            "b": {"word": p["b"]["word"], "clue": p["b"]["clue"]},
            "c": {"word": p["c"]["word"], "clue": p["c"]["clue"]},
        }
        for p in puzzles
    ]
    body = json.dumps(slim, ensure_ascii=False, indent=2)
    out = (
        "// AUTO-GENERATED by scripts/gen_puzzles.py -- do not edit by hand.\n"
        "// One entry per day: { day, date, difficulty, a:{word,clue}, "
        "b:{word,clue}, c:{word,clue} }.\n"
        "// sorted(a.word + b.word) === sorted(c.word); Ё strict; answers are "
        "never cognate/same-root.\n\n"
        "export const DAYS = " + body + ";\n\n"
        "const BY_DAY = new Map(DAYS.map((d) => [d.day, d]));\n\n"
        "export function dayIndexes() {\n  return DAYS.map((d) => d.day);\n}\n\n"
        "export function loadDay(idx) {\n  return BY_DAY.get(idx) || null;\n}\n"
    )
    days_dir = os.path.dirname(DAYS_JS_PATH)
    if os.path.isdir(days_dir):
        with open(DAYS_JS_PATH, "w", encoding="utf-8") as fh:
            fh.write(out)


def main():
    defs, source = load_words_defs()
    print(f"[gen] data source: {source}")
    print(f"[gen] usable words: {len(defs)}")

    groups = build_index(defs)
    print(f"[gen] anagram signatures: {len(groups)}")

    triples = find_splits(defs, groups)
    print(f"[gen] valid A+B==C triples found: {len(triples)}")

    unique_c = len({t['c'] for t in triples})
    print(f"[gen] unique final (C) words: {unique_c}")

    if not triples:
        print("[gen] ERROR: no valid triples; aborting.", file=sys.stderr)
        return 1

    selected = curate(triples, NUM_DAYS)
    puzzles = build_puzzles(defs, selected)
    write_outputs(puzzles)
    print(f"[gen] wrote {len(puzzles)} days -> {PUZZLES_JSON_PATH}")
    print(f"[gen] day {puzzles[0]['day']} = {puzzles[0]['date']} .. "
          f"day {puzzles[-1]['day']} = {puzzles[-1]['date']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
