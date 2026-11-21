import re

from app.services.correction import load_settings
from app.services.note_generation import build_messages, request_note

SECTIONS = ("complaint", "history", "assessment", "plan")

# Patterns that mean a statement contains a dose or schedule
DOSE_PATTERNS = [
    r"\d+(?:\.\d+)?\s*(?:mg|mcg|ml|g|milligrams?|percent)\b",
    r"\d\s*%",
    r"\b(?:once|twice|\w+ times)\s+(?:a|per|every)\s+(?:day|week|night)\b",
    r"\b(?:daily|nightly|weekly)\b",
]

DIGIT_WORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9",
}


def normalize_numbers(text):
    # "Point 1%" or "point one percent" -> "0.1%"
    text = re.sub(r"\bpoint\s+(\d)\b", r"0.\1", text, flags=re.IGNORECASE)
    return re.sub(
        r"\bpoint\s+(one|two|three|four|five|six|seven|eight|nine)\b",
        lambda m: "0." + DIGIT_WORDS[m.group(1).lower()],
        text,
        flags=re.IGNORECASE,
    )


def check_note(note, lines):
    # Returns the note (with fixes and forced flags applied) and a list of problems
    settings = load_settings()
    valid_ids = {l["id"] for l in lines}
    speaker = {l["id"]: l["speaker"] for l in lines}
    form_words = set(settings["words_after_medicine"])
    problems = []
    cited = set()

    for section in SECTIONS:
        for st in getattr(note, section):
            st.text = normalize_numbers(st.text)
            label = f'{section}: "{st.text}"'

            if not st.source_lines:
                problems.append(f"{label} has no source_lines. Add the supporting line numbers or remove the statement.")

            bad = [n for n in st.source_lines if n not in valid_ids]
            if bad:
                problems.append(f"{label} cites line numbers that do not exist: {bad}. Valid lines are {sorted(valid_ids)}.")

            valid = [n for n in st.source_lines if n in valid_ids]
            cited.update(valid)

            if section == "assessment" and valid and all(speaker[n] == "patient" for n in valid):
                problems.append(f"{label} rests only on patient lines. Assessment must only record what the doctor stated. Remove it.")

            # Forced flag: dose patterns anywhere, medicine form words in the plan only
            words = set(re.findall(r"[a-z]+", st.text.lower()))
            has_dose = any(re.search(p, st.text, re.IGNORECASE) for p in DOSE_PATTERNS)
            has_form = section == "plan" and bool(words & form_words)
            if (has_dose or has_form) and not st.needs_review:
                st.needs_review = True
                st.review_reason = st.review_reason or "Medicine or dose: doctor to confirm"

    # Every informative line must be used by at least one statement
    for l in lines:
        if l["id"] not in cited and len(l["text"].split()) >= 4:
            problems.append(
                f'Line {l["id"]} ("{l["text"]}") is not covered by any statement. '
                "Add a statement for it and cite this line. If its wording is unclear, "
                "keep the words as written and set needs_review to true."
            )

    return note, problems


def generate_checked_note(lines, max_retries=2):
    # Generate, check, and ask the model to fix problems. Returns note, leftover problems, tokens.
    messages = build_messages(lines)
    total_tokens = 0
    for attempt in range(max_retries + 1):
        note, content, tokens = request_note(messages)
        total_tokens += tokens
        note, problems = check_note(note, lines)
        if not problems:
            return note, [], total_tokens
        messages = messages + [
            {"role": "assistant", "content": content},
            {"role": "user", "content": "Fix these problems and return the full corrected note:\n- " + "\n- ".join(problems)},
        ]
    return note, problems, total_tokens   # still has problems: needs manual attention