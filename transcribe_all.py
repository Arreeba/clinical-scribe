import json
import re
import sys
import difflib
from pathlib import Path

from app.services.transcription import build_lines

# "dev" by default; run "python transcribe_all.py test" at the very end
which = sys.argv[1] if len(sys.argv) > 1 else "dev"
split = json.load(open("data/split.json", encoding="utf-8"))

out_dir = Path("data/transcripts")
out_dir.mkdir(parents=True, exist_ok=True)

NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "twelve": "12", "seventeen": "17",
}


def words(text):
    t = text.lower()
    t = t.replace("point one", "0.1")
    t = t.replace("five hundred", "500")
    t = t.replace("%", " percent")
    t = re.sub(r"(\d)\s*mg\b", r"\1 milligrams", t)
    t = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", t)
    t = re.sub(r"[^a-z0-9. ]", " ", t)
    return [NUMBER_WORDS.get(w, w) for w in t.split()]


for script_path in sorted(Path("scripts").glob("script_*.json")):
    script = json.load(open(script_path, encoding="utf-8"))
    n = script["id"]
    if n not in split[which]:
        continue

    lines = build_lines(
        f"audio/audio_{n:02d}_doctor.m4a",
        f"audio/audio_{n:02d}_patient.m4a",
    )
    json.dump(lines, open(out_dir / f"script_{n:02d}.json", "w", encoding="utf-8"), indent=2)

    expected = words(" ".join(l["text"] for l in script["lines"]))
    heard = words(" ".join(l["text"] for l in lines))
    match = difflib.SequenceMatcher(None, expected, heard)

    print(f"\nScript {n}: expected {len(script['lines'])} lines, got {len(lines)} | "
          f"word match {round(match.ratio() * 100)}%")
    for tag, i1, i2, j1, j2 in match.get_opcodes():
        if tag != "equal":
            print("  wrote:", " ".join(expected[i1:i2]) or "-",
                  "| heard:", " ".join(heard[j1:j2]) or "-")