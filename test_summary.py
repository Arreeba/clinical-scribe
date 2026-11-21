import json
import sys

from app.note_schema import Note
from app.services.summary import generate_summary

# Usage: python test_summary.py 3
n = int(sys.argv[1]) if len(sys.argv) > 1 else 1
data = json.load(open(f"data/notes/audio/script_{n:02d}.json", encoding="utf-8"))
note = Note(**data["note"])

text, problems, tokens = generate_summary(note)
print(text)
print()
print("problems left:", problems or "none")
print("tokens used:", tokens)