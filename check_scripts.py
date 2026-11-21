import json, glob
from app.note_schema import TranscriptLine

for path in sorted(glob.glob("scripts/script_*.json")):
    data = json.load(open(path, encoding="utf-8"))
    lines = [TranscriptLine(**l) for l in data["lines"]]
    ids = [l.id for l in lines]
    problems = []

    if ids != list(range(1, len(ids) + 1)):
        problems.append("line ids are not 1, 2, 3...")

    doctor_words = sum(len(l.text.split()) for l in lines if l.speaker == "doctor")
    patient_words = sum(len(l.text.split()) for l in lines if l.speaker == "patient")
    if doctor_words > 45:
        problems.append("doctor part too long")
    if patient_words > 17:
        problems.append("patient part too long")

    for item in data["checklist"]:
        for n in item["source_lines"]:
            if n not in ids:
                problems.append(f"checklist cites line {n}, which does not exist")

    facts = {item["fact"] for item in data["checklist"]}
    for f in data["must_flag"]:
        if f not in facts:
            problems.append(f"must_flag not found in checklist: {f}")

    status = "OK" if not problems else problems
    print(path, "| doctor", doctor_words, "words | patient", patient_words, "words |", status)