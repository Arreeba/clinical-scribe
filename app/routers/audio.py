import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app import models
from app.auth import get_current_doctor, get_owned_consultation, log_action
from app.database import get_db

router = APIRouter(prefix="/api/consultations", tags=["audio"])


@router.post("/{consultation_id}/audio")
def upload_audio(
    consultation_id: int,
    doctor_audio: UploadFile = File(...),
    patient_audio: UploadFile = File(...),
    db: Session = Depends(get_db),
    doctor: models.Doctor = Depends(get_current_doctor),
):
    consultation = get_owned_consultation(db, consultation_id, doctor)

    # Rule 1: no consent, no audio
    consent = db.query(models.Consent).filter_by(consultation_id=consultation.id).first()
    if consent is None:
        log_action(db, doctor.id, "audio_refused_no_consent", consultation.id)
        raise HTTPException(status_code=403, detail="Consent has not been recorded for this consultation")

    # Rule 2: one recording per consultation
    already = db.query(models.TranscriptLine).filter_by(consultation_id=consultation.id).first()
    if already is not None:
        log_action(db, doctor.id, "audio_refused_duplicate", consultation.id, "transcript already exists")
        raise HTTPException(status_code=409, detail="This consultation already has a transcript")

    log_action(db, doctor.id, "audio_uploaded", consultation.id)

    # Imported here so the server starts fast (loading torch takes a few seconds)
    from app.services.agent import load_memory, process_line
    from app.services.confidence import add_confidence_flags, build_scored_lines, drop_corrected_words
    from app.services.correction import load_settings
    from app.services.matcher import load_vocabulary
    from app.services.note_pipeline import generate_checked_note

    try:
        # 1. Save the two clips to a temporary folder, transcribe with word scores, then delete them
        with tempfile.TemporaryDirectory() as folder:
            paths = {}
            for who, upload in (("doctor", doctor_audio), ("patient", patient_audio)):
                suffix = Path(upload.filename or "").suffix or ".wav"
                path = Path(folder) / f"{who}{suffix}"
                path.write_bytes(upload.file.read())
                paths[who] = str(path)
            raw_lines = build_scored_lines(paths["doctor"], paths["patient"])

        # 2. Apply the agent's saved fixes. New guesses stay as heard, with suggestions attached.
        memory, vocabulary, settings = load_memory(), load_vocabulary(), load_settings()
        lines = []
        for line in raw_lines:
            new_text, events = process_line(line["text"], None, memory, vocabulary, settings)
            words = line["words"]
            for event in events:
                if event.get("confirmed"):   # a person confirmed this fix, so drop its scores
                    words = drop_corrected_words(words, event["original"])
            lines.append({
                "id": line["id"],
                "speaker": line["speaker"],
                "text": new_text,
                "original": line["text"],
                "corrections": events,
                "words": words,
            })

        # 3. Generate the note, with the safety checks and retries
        note, problems, tokens = generate_checked_note(lines)

        # 4. Flag statements that depend on low-confidence words
        confidence_flags = add_confidence_flags(note, lines)

        # 5. Save everything
        for line in lines:
            db.add(models.TranscriptLine(
                consultation_id=consultation.id,
                line_no=line["id"],
                speaker=line["speaker"],
                text=line["text"],
                original=line["original"],
                words=line["words"],
                corrections=line["corrections"],
            ))
        db.add(models.NoteVersion(
            consultation_id=consultation.id,
            version=1,
            content=note.model_dump(),
            saved_by=None,
            reason="generated",
        ))
        db.commit()
    except Exception as error:
        db.rollback()
        log_action(db, doctor.id, "pipeline_failed", consultation.id, str(error)[:200])
        raise HTTPException(status_code=502, detail="Processing failed. Nothing was saved.")

    log_action(db, doctor.id, "pipeline_run", consultation.id,
               f"tokens {tokens}, problems left {len(problems)}, low-confidence flags {confidence_flags}")
    return {
        "consultation_id": consultation.id,
        "status": consultation.status,
        "lines": len(lines),
        "note_version": 1,
        "tokens": tokens,
        "problems_left": problems,
        "low_confidence_flags": confidence_flags,
    }