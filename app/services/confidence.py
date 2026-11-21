import json
import re
import warnings
from pathlib import Path

import torch

from app.services.transcription import get_model

# Whisper prints a harmless warning when word scores are requested without the CUDA toolkit
warnings.filterwarnings("ignore", message="Failed to launch Triton kernels")

THRESHOLD_PATH = Path("data/confidence_settings.json")
SECTIONS = ("complaint", "history", "assessment", "plan")
PAUSE_SECONDS = 0.6   # a silence this long between two words starts a new line


def load_threshold():
    return json.load(open(THRESHOLD_PATH, encoding="utf-8"))["threshold"]


def sentence_spans(text):
    # Where each sentence starts and ends: split after . ? ! followed by a space
    spans, start = [], 0
    for m in re.finditer(r"(?<=[.?!])\s+", text):
        spans.append((start, m.start()))
        start = m.end()
    spans.append((start, len(text)))
    return [(s, e) for s, e in spans if text[s:e].strip()]


def scored_sentences(path):
    # One audio file in; lines out, each with its words and their scores
    result = get_model().transcribe(
        path, language="en", fp16=torch.cuda.is_available(), word_timestamps=True
    )
    words = [w for seg in result["segments"] for w in seg.get("words", [])]
    text = "".join(w["word"] for w in words)

    # Where each word starts inside the text
    starts, pos = [], 0
    for w in words:
        raw = w["word"]
        starts.append(pos + (len(raw) - len(raw.lstrip())))
        pos += len(raw)

    # Cut after . ? ! and also wherever the speaker paused
    cuts = {m.end() for m in re.finditer(r"(?<=[.?!])\s+", text)}
    for i in range(1, len(words)):
        if words[i]["start"] - words[i - 1]["end"] >= PAUSE_SECONDS:
            cuts.add(starts[i])

    spans, begin = [], 0
    for c in sorted(cuts):
        spans.append((begin, c))
        begin = c
    spans.append((begin, len(text)))
    spans = [(s, e) for s, e in spans if text[s:e].strip()]

    sentences = [{"text": text[s:e].strip(), "words": []} for s, e in spans]
    for w, start in zip(words, starts):
        if not w["word"].strip():
            continue
        for k, (s, e) in enumerate(spans):
            if s <= start < e:
                sentences[k]["words"].append(
                    {"word": w["word"].strip(), "score": round(float(w["probability"]), 2)}
                )
                break
    return sentences


def build_scored_lines(doctor_path, patient_path):
    # Same layout as the frozen build_lines: doctor sentences first, then patient,
    # numbered 1, 2, 3... but every line also carries its word scores
    lines = []
    for speaker, path in (("doctor", doctor_path), ("patient", patient_path)):
        for sentence in scored_sentences(path):
            lines.append({
                "id": len(lines) + 1,
                "speaker": speaker,
                "text": sentence["text"],
                "words": sentence["words"],
            })
    return lines


# Short everyday words that Whisper often scores low without being wrong
IGNORE_WORDS = {"i", "see", "it", "a", "an", "the", "but", "to", "up", "for",
                "even", "every", "and", "of", "on", "at", "in"}


def low_words(words, threshold):
    # The words scoring under the threshold, skipping punctuation and the everyday words above
    found = []
    for w in words:
        shown = w["word"].strip(" .,?!;:")
        if shown and shown.lower() not in IGNORE_WORDS and w["score"] < threshold:
            found.append({"word": shown, "score": w["score"]})
    return found


def drop_corrected_words(words, phrase):
    # If the agent fixed a phrase, a person has confirmed it, so its scores no longer matter
    target = re.sub(r"[^a-z]", "", phrase.lower())
    if not target:
        return words
    for i in range(len(words)):
        built = ""
        for j in range(i, len(words)):
            built += re.sub(r"[^a-z]", "", words[j]["word"].lower())
            if built == target:
                return words[:i] + words[j + 1:]
            if not target.startswith(built):
                break
    return words


def add_confidence_flags(note, lines, threshold=None):
    # After the note is written: flag a statement if it cites a line containing a low-score word
    # that also appears in the statement's own text
    threshold = load_threshold() if threshold is None else threshold
    low_by_line = {l["id"]: low_words(l.get("words", []), threshold) for l in lines}
    flagged = 0
    for section in SECTIONS:
        for st in getattr(note, section):
            statement_words = set(re.findall(r"[a-z0-9]+", st.text.lower()))
            found = []
            for n in st.source_lines:
                for w in low_by_line.get(n, []):
                    if re.sub(r"[^a-z0-9]", "", w["word"].lower()) in statement_words:
                        found.append(w)
            if not found:
                continue
            found = sorted(found, key=lambda w: w["score"])[:3]
            reason = "Low confidence in " + ", ".join(f"'{w['word']}' ({w['score']:.2f})" for w in found)
            st.review_reason = f"{st.review_reason} | {reason}" if st.review_reason else reason
            st.needs_review = True
            flagged += 1
    return flagged