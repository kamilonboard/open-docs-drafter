"""Word-aware keyword matching for diffs and pull request text.

Code and prose are split into lowercase words, including inside identifiers:
`dynamicISF` -> dynamic, isf; `ISFEditor` -> isf, editor; `max_iob` -> max, iob.
A keyword matches when its words appear in order. The last word may be a prefix,
so "alarm" matches `alarms`; a final -y also covers -ies, so "insulin sensitivity"
matches `insulinSensitivities`.
"""

import re

_WORD = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")


def words(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(text)]


def contains_keyword(text_words: list[str], keyword: str) -> bool:
    key = words(keyword)
    if not key:
        return False
    n = len(key)
    last = key[-1]
    if len(last) > 3 and last.endswith("y"):
        last = last[:-1]  # "sensitivity" also matches "sensitivities"
    for i in range(len(text_words) - n + 1):
        window = text_words[i : i + n]
        if window[:-1] == key[:-1] and window[-1].startswith(last):
            return True
    return False
