import re
import torch
import whisper

_model = None


def get_model(size="medium"):
    # Load the model once and reuse it, since loading takes a few seconds
    global _model
    if _model is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _model = whisper.load_model(size, device=device)
    return _model


def transcribe_file(path):
    # Audio file in, one block of text out (plain Whisper, no medicine list)
    result = get_model().transcribe(
        path,
        language="en",
        fp16=torch.cuda.is_available(),
    )
    return result["text"].strip()


def split_sentences(text):
    # Split after each full stop, question mark or exclamation mark
    parts = re.split(r"(?<=[.?!])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def build_lines(doctor_path, patient_path):
    # Doctor sentences first, then patient sentences, numbered 1, 2, 3...
    lines = []
    for speaker, path in (("doctor", doctor_path), ("patient", patient_path)):
        for sentence in split_sentences(transcribe_file(path)):
            lines.append({"id": len(lines) + 1, "speaker": speaker, "text": sentence})
    return lines