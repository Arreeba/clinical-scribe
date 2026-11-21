import json
import re
from pathlib import Path

SETTINGS_PATH = Path("data/agent_settings.json")

# Spelled-out numbers that often follow a medicine name ("ten milligrams")
NUMBER_WORDS = {
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "twenty", "fifty", "hundred", "point",
}

# Ordinary words that never belong inside a medicine name
STOP_WORDS = {
    "a", "an", "this", "that", "it", "with", "my", "your", "the", "on", "for",
    "and", "of", "to", "in", "if", "is", "not", "you", "i", "me", "at", "up",
    "any", "some",
}

MAX_SLOT_WORDS = 4


def load_settings():
    return json.load(open(SETTINGS_PATH, encoding="utf-8"))


def tokenize(text):
    # Split a sentence into words and numbers, remembering where each one sits
    tokens = []
    for m in re.finditer(r"[A-Za-z][A-Za-z'-]*|\d+(?:\.\d+)?", text):
        tokens.append({
            "text": m.group(),
            "lower": m.group().lower(),
            "start": m.start(),
            "end": m.end(),
        })
    return tokens


def is_number(word):
    return word in NUMBER_WORDS or re.fullmatch(r"\d+(?:\.\d+)?", word) is not None


def clue_after(token, settings):
    # What kind of word follows the possible medicine name?
    word = token["lower"]
    if word in settings["words_after_medicine"]:
        return "form"      # cream, gel, tablet...
    if word in settings["dose_words"]:
        return "dose"      # percent, milligrams, once...
    if is_number(word):
        return "number"    # 10, ten, 0.1...
    return None


def slot_ok(words, settings):
    # A medicine name cannot contain ordinary, form, dose or number words.
    # One exception: "a" or "an" at the start (Whisper often hears "a tepelin").
    for k, w in enumerate(words):
        word = w["lower"]
        if word in ("a", "an") and k == 0 and len(words) > 1:
            continue
        if (word in STOP_WORDS
                or word in settings["words_after_medicine"]
                or word in settings["words_before_medicine"]
                or word in settings["dose_words"]
                or is_number(word)):
            return False
    return True


def find_slots(text, settings=None):
    # Find phrases sitting where a medicine name should be:
    # after a trigger word (apply, use, take...) and before a form, dose or number.
    settings = settings or load_settings()
    tokens = tokenize(text)
    slots = []
    taken_until = -1   # stops two slots from overlapping

    for i, tok in enumerate(tokens):
        if tok["lower"] not in settings["words_before_medicine"]:
            continue
        j = i + 1
        if j <= taken_until:
            continue
        for length in range(1, MAX_SLOT_WORDS + 1):
            end = j + length
            if end >= len(tokens):
                break              # there must be a word after the phrase
            words = tokens[j:end]
            if not slot_ok(words, settings):
                continue
            clue = clue_after(tokens[end], settings)
            if clue:
                slots.append({
                    "phrase": text[words[0]["start"]:words[-1]["end"]],
                    "start": words[0]["start"],
                    "end": words[-1]["end"],
                    "before": tok["lower"],
                    "clue": clue,
                })
                taken_until = end - 1
                break              # take the shortest phrase that fits
    return slots