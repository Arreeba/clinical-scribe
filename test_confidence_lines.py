import sys

from app.services.confidence import build_scored_lines, load_threshold, low_words

n = sys.argv[1] if len(sys.argv) > 1 else "07"
lines = build_scored_lines(f"audio/audio_{n}_doctor.m4a", f"audio/audio_{n}_patient.m4a")
threshold = load_threshold()

total = low = 0
for line in lines:
    print(line["id"], line["speaker"], line["text"])
    found = low_words(line["words"], threshold)
    total += len(line["words"])
    low += len(found)
    for w in found:
        print("     low:", w["word"], w["score"])
print(f"\nScript {n}: {low} of {total} words under {threshold}")