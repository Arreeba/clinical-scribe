import json
import re
from pathlib import Path

from app.services.correction import find_slots
from app.services.matcher import suggest

MEMORY_PATH = Path("data/corrections.json")


def normalize(phrase):
    # "Mo  Meta Zone" -> "mo meta zone"
    return re.sub(r"\s+", " ", phrase.lower().strip())


def load_memory():
    if not MEMORY_PATH.exists():
        return {}
    return json.load(open(MEMORY_PATH, encoding="utf-8"))


def save_memory(memory):
    json.dump(memory, open(MEMORY_PATH, "w", encoding="utf-8"), indent=2)


def append_log(entries, log_path):
    log_path = Path(log_path)
    log = json.load(open(log_path, encoding="utf-8")) if log_path.exists() else []
    log.extend(entries)
    json.dump(log, open(log_path, "w", encoding="utf-8"), indent=2)


def apply_replacements(text, replacements):
    # Replace from the end of the sentence backwards so positions stay correct
    for start, end, new in sorted(replacements, reverse=True):
        text = text[:start] + new + text[end:]
    return text


def process_line(text, ask, memory, vocabulary, settings):
    # ask = a function that asks a person; ask=None means "apply saved fixes only"
    events = []
    replacements = []

    for slot in find_slots(text, settings):
        key = normalize(slot["phrase"])
        event = {
            "original": slot["phrase"],
            "suggestion": None,
            "candidates": [],
            "confirmed": None,
            "method": None,
            "status": None,
        }

        remembered = memory.get(key)
        if remembered and (settings["auto_apply_confirmed"] or ask is None):
            # A person confirmed this exact fix before: reuse it and mark it
            event.update(confirmed=remembered, method="memory", status="auto_applied")
        else:
            if remembered:
                result = {"status": "remembered", "candidates": [(remembered, 1.0)]}
            else:
                result = suggest(slot["phrase"], vocabulary, settings)
            if result["status"] == "ok":
                continue   # already a real medicine name

            event["candidates"] = result["candidates"]
            if result["candidates"]:
                event["suggestion"] = result["candidates"][0][0]

            if ask is None:
                event["status"] = "unreviewed"   # held-out mode: nothing new is learned
            else:
                kind, name = ask(slot["phrase"], result)
                if kind == "pick":
                    method = {
                        "respaced": "respaced_match",
                        "remembered": "memory",
                    }.get(result["status"], "spelling_and_phonetic_match")
                    event.update(confirmed=name, method=method, status="human_confirmed")
                elif kind == "typed":
                    event.update(confirmed=name, method="typed_by_reviewer", status="human_typed")
                else:
                    event["status"] = "rejected" if result["candidates"] else "unidentified_skipped"

                if event["confirmed"]:
                    memory[key] = event["confirmed"]   # remember it for next time
                    save_memory(memory)

        if event["confirmed"]:
            replacements.append((slot["start"], slot["end"], event["confirmed"]))
        events.append(event)

    return apply_replacements(text, replacements), events