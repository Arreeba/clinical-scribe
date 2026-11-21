import difflib
import json
from pathlib import Path

import jellyfish

from app.services.correction import load_settings

DRUG_LIST_PATH = Path("data/drug_list.json")


def load_vocabulary():
    return json.load(open(DRUG_LIST_PATH, encoding="utf-8"))


def squash(text):
    # "mo meta zone" -> "mometazone" (letters only, no spaces)
    return "".join(ch for ch in text.lower() if ch.isalpha())


def sound(text):
    # A short code for how a word sounds, so "mometazone" and "mometasone" match
    try:
        return jellyfish.metaphone(text)
    except Exception:
        return ""


def similarity(heard, name):
    # Half spelling similarity, half sound similarity (0 to 1)
    spelling = difflib.SequenceMatcher(None, heard, name).ratio()
    sounds = difflib.SequenceMatcher(None, sound(heard), sound(name)).ratio()
    return 0.5 * spelling + 0.5 * sounds


def heard_forms(phrase):
    # The phrase squashed together, plus a version without a leading "a" or "an"
    # (Whisper hears "a tepelin" for "adapalene", but sometimes the "a" is extra)
    words = phrase.lower().split()
    forms = [squash(phrase)]
    if len(words) > 1 and words[0] in ("a", "an"):
        forms.append(squash(" ".join(words[1:])))
    return forms


def suggest(phrase, vocabulary=None, settings=None):
    vocabulary = vocabulary or load_vocabulary()
    settings = settings or load_settings()
    names = set(vocabulary)
    forms = heard_forms(phrase)

    # 1. Already a real name, written normally: leave it alone
    if phrase.lower().strip() in names:
        return {"status": "ok", "candidates": []}

    # 2. Right letters, wrong spacing ("calci potriol")
    by_letters = {squash(n): n for n in vocabulary}
    if forms[0] in by_letters:
        return {"status": "respaced", "candidates": [(by_letters[forms[0]], 1.0)]}

    # 3. Score every name, keep the ones above the minimum score
    scored = []
    for name in vocabulary:
        key = squash(name)
        score = max(similarity(form, key) for form in forms)
        if score >= settings["min_score"]:
            scored.append((name, score))
    scored.sort(key=lambda pair: pair[1], reverse=True)

    # Drop salt variants ("mometasone furoate" next to "mometasone")
    kept = []
    for name, score in scored:
        key = squash(name)
        if any(key.startswith(squash(k)) or squash(k).startswith(key) for k, _ in kept):
            continue
        kept.append((name, score))

    kept = [(n, round(s, 2)) for n, s in kept[:settings["top_k"]]]

    # 4. Nothing close enough: say so, don't force a guess
    if not kept:
        return {"status": "unidentified", "candidates": []}
    return {"status": "suggested", "candidates": kept}