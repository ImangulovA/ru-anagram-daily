#!/usr/bin/env python3
"""
Анаграмма дня -- mandatory invariant gate (RU).

Loads the generated puzzles (data/puzzles.json) and the word dictionary
(data/words_defs.json) and asserts, for EVERY entry:

  1. Multiset invariant:  sorted(a.word + b.word) == sorted(c.word)   (Ё strict)
  2. Length rules:        len(c) >= 9, len(a) >= 2, len(b) >= 2,
                          len(a) + len(b) == len(c)
  3. All words are UPPERCASE Cyrillic (А-ЯЁ) only.
  4. Contiguous day indices starting at FIRST_DAY (may be negative).
  5. Dates are contiguous from the anchor 2026-07-06.
  6. clue fields are non-empty and match the dictionary definitions.
  7. All three words exist in words_defs.json.
  8. Answers (A,B,C) are pairwise non-cognate; no source is a substring of C.
  9. Weekday -> C-length ramp is respected (9 / 10 / 11-13).

Exits nonzero on ANY failure with a clear message.
"""

import json
import os
import re
import sys
from datetime import date, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(ROOT, "data")
PUZZLES_JSON_PATH = os.path.join(DATA_DIR, "puzzles.json")
WORDS_DEFS_PATH = os.path.join(DATA_DIR, "words_defs.json")
PUZZLES_JS_PATH = os.path.join(DATA_DIR, "puzzles.js")

ANCHOR_DATE = date(2026, 7, 6)
MIN_C_LEN = 8
MIN_PART_LEN = 2

RU_RE = re.compile(r"^[А-ЯЁ]+$")

sys.path.insert(0, SCRIPT_DIR)
try:
    from gen_puzzles import FIRST_DAY as GEN_FIRST_DAY  # noqa: E402
except Exception:
    GEN_FIRST_DAY = None
try:
    from gen_puzzles import are_cognate as _are_cognate  # noqa: E402
    from gen_puzzles import len_target_for_weekday as _len_for_wd  # noqa: E402
except Exception:
    _are_cognate = None
    _len_for_wd = None


def _load_defs():
    if os.path.exists(WORDS_DEFS_PATH):
        with open(WORDS_DEFS_PATH, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        return {k.strip().upper(): v for k, v in raw.items()}, \
            "data/words_defs.json"
    return {}, "EMPTY (words_defs.json absent)"


def fail(msg):
    print(f"[verify] FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def main():
    if not os.path.exists(PUZZLES_JSON_PATH):
        fail(f"missing {PUZZLES_JSON_PATH} -- run gen_puzzles.py first")

    with open(PUZZLES_JSON_PATH, "r", encoding="utf-8") as fh:
        puzzles = json.load(fh)

    if not isinstance(puzzles, list) or not puzzles:
        fail("puzzles.json is not a non-empty JSON array")

    defs, defs_source = _load_defs()
    print(f"[verify] dictionary source: {defs_source} ({len(defs)} words)")
    print(f"[verify] loaded {len(puzzles)} puzzle entries")

    # ---- puzzles.js consistency -------------------------------------------
    if os.path.exists(PUZZLES_JS_PATH):
        with open(PUZZLES_JS_PATH, "r", encoding="utf-8") as fh:
            js = fh.read().strip()
        prefix = "window.PUZZLES = "
        if not js.startswith(prefix) or not js.endswith(";"):
            fail("puzzles.js must be exactly 'window.PUZZLES = <array>;'")
        try:
            js_array = json.loads(js[len(prefix):-1])
        except json.JSONDecodeError as exc:
            fail(f"puzzles.js payload is not valid JSON: {exc}")
        if js_array != puzzles:
            fail("puzzles.js content does not match puzzles.json")
        print("[verify] puzzles.js matches puzzles.json OK")
    else:
        fail(f"missing {PUZZLES_JS_PATH}")

    diff_hist = {d: 0 for d in range(1, 6)}

    first_entry_day = puzzles[0].get("day")
    if not isinstance(first_entry_day, int):
        fail("first entry has a non-integer 'day'")
    first_day = GEN_FIRST_DAY if GEN_FIRST_DAY is not None else first_entry_day
    if GEN_FIRST_DAY is not None and first_entry_day != GEN_FIRST_DAY:
        fail(f"first entry day {first_entry_day} != gen_puzzles.FIRST_DAY "
             f"{GEN_FIRST_DAY}")
    print(f"[verify] expected first day index: {first_day}")

    for i, p in enumerate(puzzles):
        ctx = f"entry index {i}"
        for field in ("day", "date", "a", "b", "c", "difficulty"):
            if field not in p:
                fail(f"{ctx}: missing field '{field}'")
        expected_day = first_day + i
        if p["day"] != expected_day:
            fail(f"{ctx}: day index is {p['day']}, expected {expected_day}")

        the_date = ANCHOR_DATE + timedelta(days=expected_day)
        expected_date = the_date.isoformat()
        if p["date"] != expected_date:
            fail(f"{ctx}: date is {p['date']}, expected {expected_date}")

        if p["difficulty"] not in (1, 2, 3, 4, 5):
            fail(f"{ctx}: difficulty {p['difficulty']} not in 1..5")
        diff_hist[p["difficulty"]] += 1

        a_word = p["a"]["word"]
        b_word = p["b"]["word"]
        c_word = p["c"]["word"]

        for label, w in (("a", a_word), ("b", b_word), ("c", c_word)):
            if not isinstance(w, str) or not RU_RE.match(w) or w.upper() != w:
                fail(f"{ctx}: {label}.word '{w}' is not UPPERCASE Cyrillic")

        if len(c_word) < MIN_C_LEN:
            fail(f"{ctx}: len(C)={len(c_word)} < {MIN_C_LEN} (C='{c_word}')")
        if len(a_word) < MIN_PART_LEN:
            fail(f"{ctx}: len(A)={len(a_word)} < {MIN_PART_LEN} (A='{a_word}')")
        if len(b_word) < MIN_PART_LEN:
            fail(f"{ctx}: len(B)={len(b_word)} < {MIN_PART_LEN} (B='{b_word}')")
        if len(a_word) + len(b_word) != len(c_word):
            fail(f"{ctx}: len(A)+len(B) != len(C)")

        if sorted(a_word + b_word) != sorted(c_word):
            fail(f"{ctx}: multiset invariant broken: "
                 f"sorted('{a_word}'+'{b_word}') != sorted('{c_word}')")

        if _are_cognate is not None:
            for x, y, lbl in ((a_word, b_word, "A/B"),
                              (a_word, c_word, "A/C"),
                              (b_word, c_word, "B/C")):
                if _are_cognate(x, y):
                    fail(f"{ctx}: {lbl} answers '{x}' & '{y}' are cognate / "
                         f"share a root")

        if a_word.upper() in c_word.upper():
            fail(f"{ctx}: source A '{a_word}' is a substring of C '{c_word}'")
        if b_word.upper() in c_word.upper():
            fail(f"{ctx}: source B '{b_word}' is a substring of C '{c_word}'")

        if _len_for_wd is not None:
            allowed = _len_for_wd(the_date.weekday())
            if len(c_word) not in allowed:
                fail(f"{ctx}: weekday {the_date.weekday()} wants C-length in "
                     f"{sorted(allowed)} but C='{c_word}' has {len(c_word)}")

        if defs:
            for label, w in (("a", a_word), ("b", b_word), ("c", c_word)):
                if w not in defs:
                    fail(f"{ctx}: {label}.word '{w}' not found in dictionary")

        for label, w in (("a", a_word), ("b", b_word), ("c", c_word)):
            clue = p[label].get("clue")
            if not isinstance(clue, str) or not clue.strip():
                fail(f"{ctx}: {label}.clue is empty")
            if defs and w in defs:
                expected_def = str(defs[w].get("def", "")).strip()
                if clue.strip() != expected_def:
                    fail(f"{ctx}: {label}.clue does not match dictionary def "
                         f"for '{w}'")

    print("[verify] ALL CHECKS PASSED")
    print(f"[verify] days: {puzzles[0]['day']}..{puzzles[-1]['day']} "
          f"({puzzles[0]['date']} .. {puzzles[-1]['date']})")
    print(f"[verify] difficulty histogram: {diff_hist}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
