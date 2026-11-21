import json
import os
import time

from dotenv import load_dotenv
from groq import Groq, RateLimitError

from app.note_schema import Note

load_dotenv()
client = Groq(api_key=os.environ["GROQ_API_KEY"])
MODEL = "openai/gpt-oss-120b"

SYSTEM_PROMPT = """You write structured clinical notes from a numbered transcript of a doctor-patient consultation. A doctor will review everything you write.

Rules:
1. Use only what is said in the transcript. Never add facts and never guess.
2. Never diagnose. Leave "assessment" empty unless the doctor explicitly states an assessment or diagnosis aloud. If they do, record it as what the doctor said.
3. Sections: complaint (what troubles the patient and for how long), history (background, triggers, past treatments, and any question the patient asked, written as "Patient asked ..."), assessment (only if the doctor stated one), plan (medicines, doses, advice and follow-up).
4. One short, plain fact per statement.
5. Every statement lists the transcript line numbers that support it in source_lines. Never leave it empty and use only line numbers that exist. If a statement only makes sense together with an earlier line (for example the patient says "it" or "this"), cite that earlier line too.
6. Do not answer a patient's question, even if you know the answer. Only record that it was asked.
7. Set needs_review to true for any statement that contains a medicine name, strength, dose, how often it is taken, or how long to take it. Do not flag follow-up visit timing, general advice, or how long a symptom has lasted. Write the medicine name exactly as it appears in the transcript. Use the review_reason "Medicine or dose: doctor to confirm".
8. The transcript comes from speech recognition and may contain misheard words. Check every line: does each word make sense in this medical context? Body parts and places must fit the complaint, and ordinary words must fit the sentence. If a word looks like a mishearing, keep it exactly as written in the statement and set needs_review to true. If you are confident what it should be, say so in review_reason, for example "'angle' may be 'ankle'". If you are not, write "unclear word: verify with doctor" and do not guess. Never correct the word yourself in the statement.
9. When needs_review is false, review_reason must be an empty string.
10. Write each statement in neutral clinical style so that it makes sense on its own. Do not copy the doctor's direct address: replace "you", "your", "I" and "it" with neutral wording, for example "Dry skin on your hands" becomes "Dry skin on the hands". Plan statements may be short instructions, such as "Keep feet dry". Keep medicine names, doses and any suspicious words exactly as they appear in the transcript. If a patient's words such as "this" or "it" do not name the thing in the same line, keep the patient's own words, for example "Patient asked whether this can be taken at night", and do not fill in a name.
11. Never drop information silently. Every line that carries information must be covered by at least one statement. If a sentence is unclear or contains a word that makes no sense, still write a statement for it using the words as written, set needs_review to true, and say why. If a line mixes a clear part and an unclear part, keep both parts."""

# Hand-written JSON schema. Groq's strict mode needs every field listed as
# required and no extra fields allowed.
STATEMENT = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "source_lines": {"type": "array", "items": {"type": "integer"}},
        "needs_review": {"type": "boolean"},
        "review_reason": {"type": "string"},
    },
    "required": ["text", "source_lines", "needs_review", "review_reason"],
    "additionalProperties": False,
}

NOTE_SCHEMA = {
    "type": "object",
    "properties": {
        "complaint": {"type": "array", "items": STATEMENT},
        "history": {"type": "array", "items": STATEMENT},
        "assessment": {"type": "array", "items": STATEMENT},
        "plan": {"type": "array", "items": STATEMENT},
    },
    "required": ["complaint", "history", "assessment", "plan"],
    "additionalProperties": False,
}


def format_transcript(lines):
    # Only the id, speaker and text go to the model. Nothing else, ever.
    return "\n".join(f'{l["id"]}. {l["speaker"]}: {l["text"]}' for l in lines)


def build_messages(lines):
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "Transcript:\n" + format_transcript(lines)},
    ]


def request_note(messages, model=MODEL):
    # One request to the model. Waits and retries if the rate limit is hit.
    for attempt in range(3):
        try:
            reply = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0,
                reasoning_effort="low",
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "clinical_note", "strict": True, "schema": NOTE_SCHEMA},
                },
            )
            content = reply.choices[0].message.content
            return Note(**json.loads(content)), content, reply.usage.total_tokens
        except RateLimitError:
            print("Rate limit reached, waiting 20 seconds...")
            time.sleep(20)
    raise RuntimeError("Groq rate limit: gave up after 3 tries")


def generate_note(lines, model=MODEL):
    note, _, tokens = request_note(build_messages(lines), model)
    return note, tokens