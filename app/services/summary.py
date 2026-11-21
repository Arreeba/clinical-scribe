import json
import re
import time

from groq import RateLimitError

from app.services.matcher import load_vocabulary
from app.services.note_generation import MODEL, client
from app.services.note_pipeline import SECTIONS

# Fixed wording, written by our code and never by the model
FOOTER = ("This summary was prepared from your doctor's approved notes. "
          "If you are unsure about anything, please contact your clinic.")

SUMMARY_PROMPT = """You write a short after-visit summary for a patient from a doctor's approved consultation note. The patient will read it at home.

Rules:
1. Use only facts that are in the note. Never add a fact, medicine, dose, duration, warning, side effect, appointment or piece of advice that is not in the note.
2. Write in simple, warm, everyday words, speaking to the patient as "you". Use complete sentences, not note fragments.
3. Keep every medicine name, strength, how often and how long exactly as written in the note.
4. Never diagnose. Do not name or explain a condition unless the note names it.
5. why_you_came: one complete sentence in this form: "You came in because of [the complaint] that has lasted [how long]." Leave out "that has lasted ..." if the note gives no duration.
6. what_you_told_us: each background fact the patient reported (things they do, tried or noticed), as a sentence to "you". Do not put questions here, and do not repeat the complaint.
7. medicines: one entry per medicine in the plan, in this form: "[Medicine name and strength]. [How to use it, how often, how long]. [Only if the note says so: an instruction to finish the whole course, even if the skin clears sooner]."
8. other_instructions: advice from the plan that is not a medicine and not a follow-up visit.
9. follow_up: return visits and any urgent-care instruction, only if they are in the note.
10. questions: each question the patient asked, written as a sentence to the patient in this form: "You asked whether [the question]." Never answer it. If a question uses a word like "it" or "this" and another statement in the note makes clear what it means, put that statement in what_you_told_us so the question makes sense. If the note does not make it clear, keep the patient's words and do not guess.
11. If a part has nothing in the note, return an empty list (or an empty string for why_you_came).
12. Do not mention flags, reviews or transcripts."""

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "why_you_came": {"type": "string"},
        "what_you_told_us": {"type": "array", "items": {"type": "string"}},
        "medicines": {"type": "array", "items": {"type": "string"}},
        "other_instructions": {"type": "array", "items": {"type": "string"}},
        "follow_up": {"type": "array", "items": {"type": "string"}},
        "questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["why_you_came", "what_you_told_us", "medicines",
                 "other_instructions", "follow_up", "questions"],
    "additionalProperties": False,
}

LIST_KEYS = ("what_you_told_us", "medicines", "other_instructions", "follow_up", "questions")

# Words that suggest a diagnosis or extra advice. Rejected unless the note has them.
BANNED = [r"diagnos", r"suffering from", r"caused by", r"sign of", r"likely",
          r"may be due to", r"side effects?", r"serious"]

NUMBER_WORDS = {
    "zero": "0", "one": "1", "once": "1", "two": "2", "twice": "2", "three": "3",
    "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "twelve": "12", "seventeen": "17", "twenty": "20", "fifty": "50",
}


def format_note(note):
    # Only the statement text goes to the model. No source lines, no flags.
    rows = []
    for section in SECTIONS:
        for st in getattr(note, section):
            rows.append(f"{section}: {st.text}")
    return "\n".join(rows)


def numbers_in(text):
    t = text.lower().replace("five hundred", "500")
    t = re.sub(r"\b[a-z]+\b", lambda m: NUMBER_WORDS.get(m.group(), m.group()), t)
    return set(re.findall(r"\d+(?:\.\d+)?", t))


def summary_text(summary):
    parts = [summary["why_you_came"]]
    for key in LIST_KEYS:
        parts.extend(summary[key])
    return " ".join(p for p in parts if p)


def check_summary(summary, note_text):
    problems = []
    text = summary_text(summary)
    low_note = note_text.lower()
    low_text = text.lower()

    extra = numbers_in(text) - numbers_in(note_text)
    if extra:
        problems.append(f"The summary contains numbers that are not in the note: {sorted(extra)}. Use only the numbers in the note.")

    for name in load_vocabulary():
        if re.search(r"\b" + re.escape(name) + r"\b", low_text) and not re.search(r"\b" + re.escape(name) + r"\b", low_note):
            problems.append(f'The summary mentions "{name}", which is not in the note. Remove it.')

    for pattern in BANNED:
        if re.search(pattern, low_text) and not re.search(pattern, low_note):
            problems.append(f'The summary uses wording matching "{pattern}", which is not in the note. Remove it.')

    return problems


def bullets(items):
    return "\n".join("- " + item for item in items)


def render(summary):
    # Lays out the final text. The headings and the closing sentence come from this code.
    blocks = []
    if summary["why_you_came"]:
        blocks.append("Why you came in\n" + summary["why_you_came"])
    if summary["what_you_told_us"]:
        blocks.append("What you told us\n" + bullets(summary["what_you_told_us"]))
    if summary["medicines"]:
        heading = "Your medicine" if len(summary["medicines"]) == 1 else "Your medicines"
        blocks.append(heading + "\n" + "\n".join(summary["medicines"]))
    if summary["other_instructions"]:
        blocks.append("Other instructions\n" + bullets(summary["other_instructions"]))
    if summary["follow_up"]:
        blocks.append("Follow-up\n" + bullets(summary["follow_up"]))
    if summary["questions"]:
        many = len(summary["questions"]) > 1
        blocks.append(("Your questions" if many else "Your question") + "\n" + bullets(summary["questions"]))
    blocks.append(FOOTER)
    return "\n\n".join(blocks)


def request_summary(messages):
    for attempt in range(3):
        try:
            reply = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=0,
                reasoning_effort="low",
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "patient_summary", "strict": True, "schema": SUMMARY_SCHEMA},
                },
            )
            content = reply.choices[0].message.content
            return json.loads(content), content, reply.usage.total_tokens
        except RateLimitError:
            print("Rate limit reached, waiting 20 seconds...")
            time.sleep(20)
    raise RuntimeError("Groq rate limit: gave up after 3 tries")


def generate_summary(note, max_retries=2):
    # The note must be an APPROVED note. The API enforces that before calling this.
    note_text = format_note(note)
    messages = [
        {"role": "system", "content": SUMMARY_PROMPT},
        {"role": "user", "content": "Approved note:\n" + note_text},
    ]
    total_tokens = 0
    for attempt in range(max_retries + 1):
        summary, content, tokens = request_summary(messages)
        total_tokens += tokens
        problems = check_summary(summary, note_text)
        if not problems:
            return render(summary), [], total_tokens
        messages = messages + [
            {"role": "assistant", "content": content},
            {"role": "user", "content": "Fix these problems and return the full corrected summary:\n- " + "\n- ".join(problems)},
        ]
    return render(summary), problems, total_tokens   # still has problems: needs manual attention