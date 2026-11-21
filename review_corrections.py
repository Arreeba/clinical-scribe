import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from app.services.agent import append_log, load_memory, process_line
from app.services.correction import load_settings
from app.services.matcher import load_vocabulary

# "dev" asks you questions and learns. "test" only applies saved fixes (held-out run).
which = sys.argv[1] if len(sys.argv) > 1 else "dev"
split = json.load(open("data/split.json", encoding="utf-8"))
settings = load_settings()
vocabulary = load_vocabulary()
memory = load_memory()

in_dir = Path("data/transcripts")
out_dir = Path("data/transcripts_corrected")
out_dir.mkdir(parents=True, exist_ok=True)
log_path = "data/correction_log.json" if which == "dev" else "data/correction_log_test.json"

current = {"script": None, "line": None, "text": ""}


def ask(phrase, result):
    print(f'\nScript {current["script"]}, line {current["line"]}: "{current["text"]}"')
    print(f"  heard: {phrase!r}")
    candidates = result["candidates"]
    if candidates:
        for k, (name, score) in enumerate(candidates, start=1):
            print(f"  {k}) {name} ({score})")
        print("  (a score shows similarity, not certainty)")
        prompt = f"  Type 1-{len(candidates)} to accept, type the correct name, or press Enter to skip: "
    else:
        print("  No close match in the vocabulary.")
        prompt = "  Type the correct name, or press Enter to skip: "

    answer = input(prompt).strip()
    if not answer:
        return "skip", None
    if answer.isdigit():
        if 1 <= int(answer) <= len(candidates):
            return "pick", candidates[int(answer) - 1][0]
        print("  Not a valid choice, skipping.")
        return "skip", None
    return "typed", answer


ask_fn = ask if which == "dev" else None
if which != "dev":
    print("Held-out mode: applying saved corrections only. Nothing new will be learned.")

totals = Counter()

for n in split[which]:
    path = in_dir / f"script_{n:02d}.json"
    if not path.exists():
        print(f"Script {n}: no transcript found, skipping")
        continue

    lines = json.load(open(path, encoding="utf-8"))
    output, log_entries = [], []

    for line in lines:
        current.update(script=n, line=line["id"], text=line["text"])
        new_text, events = process_line(line["text"], ask_fn, memory, vocabulary, settings)

        for e in events:
            e.update(script=n, line_id=line["id"], time=datetime.now().isoformat(timespec="seconds"))
            totals[e["status"]] += 1
            if e["status"] == "auto_applied":
                print(f'  auto-applied (script {n}, line {line["id"]}): {e["original"]!r} -> {e["confirmed"]!r}')

        log_entries.extend(events)
        output.append({
            "id": line["id"],
            "speaker": line["speaker"],
            "text": new_text,
            "original": line["text"],
            "corrections": events,
        })

    json.dump(output, open(out_dir / f"script_{n:02d}.json", "w", encoding="utf-8"), indent=2)
    append_log(log_entries, log_path)

print("\nDone. Cleaned transcripts are in data/transcripts_corrected")
print("Summary:", dict(totals))