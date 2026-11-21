import json
import sys
import time
from pathlib import Path

from app.services.note_pipeline import SECTIONS, generate_checked_note

# "dev" by default. "test" is for the held-out scripts, at the very end only.
which = sys.argv[1] if len(sys.argv) > 1 else "dev"
split = json.load(open("data/split.json", encoding="utf-8"))

out_dir = Path("data/notes") if which == "dev" else Path("data/notes_test")
(out_dir / "audio").mkdir(parents=True, exist_ok=True)

PAUSE = 15   # seconds between calls, to stay under 8,000 tokens per minute

sheet = []
total_tokens = 0
first_call = True

for n in split[which]:
    path = Path(f"data/transcripts_corrected/script_{n:02d}.json")
    if not path.exists():
        print(f"Script {n}: no corrected transcript found, skipping")
        continue

    lines = json.load(open(path, encoding="utf-8"))
    script = json.load(open(f"scripts/script_{n:02d}.json", encoding="utf-8"))
    checklist = [c["fact"] if isinstance(c, dict) else c for c in script["checklist"]]

    if not first_call:
        time.sleep(PAUSE)
    first_call = False

    note, problems, tokens = generate_checked_note(lines)
    total_tokens += tokens

    json.dump(
        {"note": note.model_dump(), "problems": problems, "tokens": tokens},
        open(out_dir / "audio" / f"script_{n:02d}.json", "w", encoding="utf-8"),
        indent=2,
    )

    statements = [(s, st) for s in SECTIONS for st in getattr(note, s)]
    flagged = sum(1 for _, st in statements if st.needs_review)
    print(f"Script {n}: {len(statements)} statements, {flagged} flagged, "
          f"{len(problems)} problems left, {tokens} tokens")

    sheet.append(f"## Script {n}\n")
    sheet.append("Checklist (tick each fact that is in the note):\n")
    sheet.extend(f"- [ ] {fact}" for fact in checklist)
    sheet.append("\nNote:\n")
    for section, st in statements:
        flag = f"  FLAG: {st.review_reason}" if st.needs_review else ""
        lines_txt = ",".join(str(x) for x in st.source_lines)
        sheet.append(f"- [{section}] {st.text} (lines {lines_txt}){flag}")
    if problems:
        sheet.append(f"\nProblems left: {problems}")
    sheet.append("\nMissed facts: ___   Invented statements: ___   Odd words flagged: ___   False flags: ___\n")

(out_dir / "review_sheet.md").write_text("\n".join(sheet), encoding="utf-8")
print(f"\nTotal tokens: {total_tokens}")
print(f"Review sheet: {out_dir / 'review_sheet.md'}")