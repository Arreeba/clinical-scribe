import json
import sys

from app.services.note_pipeline import generate_checked_note

# Usage: python test_note.py 1           (script text)
#        python test_note.py 8 corrected (agent-corrected Whisper transcript)
n = int(sys.argv[1]) if len(sys.argv) > 1 else 1
source = sys.argv[2] if len(sys.argv) > 2 else "script"

if source == "script":
    lines = json.load(open(f"scripts/script_{n:02d}.json", encoding="utf-8"))["lines"]
else:
    lines = json.load(open(f"data/transcripts_corrected/script_{n:02d}.json", encoding="utf-8"))

note, problems, tokens = generate_checked_note(lines)
print(note.model_dump_json(indent=2))
print("problems left:", problems or "none")
print("tokens used:", tokens)