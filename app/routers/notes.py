import copy
import re
from datetime import datetime
from app.services.confidence import load_threshold, low_words

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import get_current_doctor, get_owned_consultation, log_action
from app.database import get_db
from app.note_schema import Note, can_move
from app.services.agent import append_log, load_memory, normalize, save_memory

router = APIRouter(prefix="/api/consultations", tags=["notes"])

SECTIONS = ("complaint", "history", "assessment", "plan")


def latest_version(db, consultation_id):
    return (
        db.query(models.NoteVersion)
        .filter_by(consultation_id=consultation_id)
        .order_by(models.NoteVersion.version.desc())
        .first()
    )


def note_out(consultation, version):
    return schemas.NoteOut(
        consultation_id=consultation.id,
        status=consultation.status,
        version=version.version,
        reason=version.reason,
        note=version.content,
    )


def require_unlocked(db, consultation, doctor, what):
    # The lock: once a note is approved, nothing may change it
    if not can_move(consultation.status, "edited"):
        log_action(db, doctor.id, "edit_rejected_locked", consultation.id, what)
        raise HTTPException(status_code=409, detail="This note is approved and locked. It cannot be changed.")


@router.get("/{consultation_id}/transcript", response_model=list[schemas.TranscriptLineOut])
def get_transcript(
    consultation_id: int,
    db: Session = Depends(get_db),
    doctor: models.Doctor = Depends(get_current_doctor),
):
    consultation = get_owned_consultation(db, consultation_id, doctor)
    rows = (
        db.query(models.TranscriptLine)
        .filter_by(consultation_id=consultation.id)
        .order_by(models.TranscriptLine.line_no)
        .all()
    )
    log_action(db, doctor.id, "transcript_viewed", consultation.id)
    threshold = load_threshold()
    return [
        schemas.TranscriptLineOut(
            line_no=r.line_no, speaker=r.speaker, text=r.text,
            original=r.original, corrections=r.corrections,
            words=r.words, low_words=low_words(r.words, threshold),
        )
        for r in rows
    ]


@router.get("/{consultation_id}/note", response_model=schemas.NoteOut)
def get_note(
    consultation_id: int,
    db: Session = Depends(get_db),
    doctor: models.Doctor = Depends(get_current_doctor),
):
    consultation = get_owned_consultation(db, consultation_id, doctor)
    latest = latest_version(db, consultation.id)
    if latest is None:
        raise HTTPException(status_code=404, detail="No note yet. Upload the audio first.")
    log_action(db, doctor.id, "note_viewed", consultation.id)
    return note_out(consultation, latest)


@router.get("/{consultation_id}/versions", response_model=list[schemas.VersionOut])
def list_versions(
    consultation_id: int,
    db: Session = Depends(get_db),
    doctor: models.Doctor = Depends(get_current_doctor),
):
    consultation = get_owned_consultation(db, consultation_id, doctor)
    log_action(db, doctor.id, "versions_viewed", consultation.id)
    return (
        db.query(models.NoteVersion)
        .filter_by(consultation_id=consultation.id)
        .order_by(models.NoteVersion.version)
        .all()
    )


@router.put("/{consultation_id}/note", response_model=schemas.NoteOut)
def edit_note(
    consultation_id: int,
    note: Note,
    db: Session = Depends(get_db),
    doctor: models.Doctor = Depends(get_current_doctor),
):
    consultation = get_owned_consultation(db, consultation_id, doctor)
    require_unlocked(db, consultation, doctor, "note edit attempt")
    latest = latest_version(db, consultation.id)
    if latest is None:
        raise HTTPException(status_code=404, detail="No note yet. Upload the audio first.")

    # Refuse an empty note, which is what a wrongly shaped request would produce
    if sum(len(getattr(note, s)) for s in SECTIONS) == 0:
        raise HTTPException(status_code=422, detail="The note has no statements. Send the whole note with its four sections.")

    # Every cited line number must exist in this consultation's transcript
    
    line_numbers = {
        r.line_no for r in db.query(models.TranscriptLine).filter_by(consultation_id=consultation.id)
    }
    for section in SECTIONS:
        for st in getattr(note, section):
            bad = [n for n in st.source_lines if n not in line_numbers]
            if bad:
                raise HTTPException(status_code=422, detail=f"Line numbers {bad} do not exist in this transcript")

    version = models.NoteVersion(
        consultation_id=consultation.id,
        version=latest.version + 1,
        content=note.model_dump(),
        saved_by=doctor.id,
        reason="edited",
    )
    consultation.status = "edited"
    db.add(version)
    db.commit()
    db.refresh(version)
    log_action(db, doctor.id, "note_edited", consultation.id, f"version {version.version}")
    return note_out(consultation, version)


@router.put("/{consultation_id}/approve", response_model=schemas.NoteOut)
def approve_note(
    consultation_id: int,
    db: Session = Depends(get_db),
    doctor: models.Doctor = Depends(get_current_doctor),
):
    consultation = get_owned_consultation(db, consultation_id, doctor)
    if not can_move(consultation.status, "approved"):
        log_action(db, doctor.id, "approve_rejected", consultation.id, f"status is {consultation.status}")
        raise HTTPException(status_code=409, detail="This note is already approved")
    latest = latest_version(db, consultation.id)
    if latest is None:
        raise HTTPException(status_code=404, detail="No note yet. Upload the audio first.")

    still_flagged = sum(
        1 for section in SECTIONS for st in latest.content[section] if st.get("needs_review")
    )
    version = models.NoteVersion(
        consultation_id=consultation.id,
        version=latest.version + 1,
        content=latest.content,
        saved_by=doctor.id,
        reason="approved",
    )
    consultation.status = "approved"
    db.add(version)
    db.commit()
    db.refresh(version)
    log_action(db, doctor.id, "note_approved", consultation.id,
               f"version {version.version}, {still_flagged} statements still flagged")
    return note_out(consultation, version)

def replace_phrase(text, original, confirmed):
    # Replace the phrase as heard. If it isn't found, try it without a leading "a" or "an"
    # (the note writer often drops it). Spaces and hyphens count as the same thing.
    words = re.findall(r"[A-Za-z0-9']+", original)
    variants = [words]
    if len(words) > 1 and words[0].lower() in ("a", "an"):
        variants.append(words[1:])
    for variant in variants:
        pattern = re.compile(
            r"\b" + r"[\s\-]*".join(re.escape(w) for w in variant) + r"\b", re.IGNORECASE
        )
        new_text, count = pattern.subn(confirmed, text)
        if count:
            return new_text, True
    return text, False

@router.post("/{consultation_id}/corrections", response_model=schemas.NoteOut)
def confirm_correction(
    consultation_id: int,
    data: schemas.CorrectionConfirm,
    db: Session = Depends(get_db),
    doctor: models.Doctor = Depends(get_current_doctor),
):
    consultation = get_owned_consultation(db, consultation_id, doctor)
    require_unlocked(db, consultation, doctor, "correction attempt")

    row = (
        db.query(models.TranscriptLine)
        .filter_by(consultation_id=consultation.id, line_no=data.line_no)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="That transcript line does not exist")
    new_line_text, found = replace_phrase(row.text, data.original, data.confirmed)
    if not found:
        raise HTTPException(status_code=422, detail="That phrase is not in this line")

    # 1. Record the decision on the transcript line, and fix the text
    corrections = [dict(c) for c in row.corrections]
    entry = next((c for c in corrections if c["original"].lower() == data.original.lower()), None)
    suggested = [name.lower() for name, _ in entry["candidates"]] if entry else []
    typed = data.confirmed.lower() not in suggested
    if entry is None:
        entry = {"original": data.original, "suggestion": None, "candidates": []}
        corrections.append(entry)
    entry["confirmed"] = data.confirmed
    entry["method"] = "typed_by_reviewer" if typed else "spelling_and_phonetic_match"
    entry["status"] = "human_typed" if typed else "human_confirmed"
    row.text = new_line_text
    row.corrections = corrections

    # 2. Apply the same fix to every note statement that cites this line
    latest = latest_version(db, consultation.id)
    if latest is not None:
        content = copy.deepcopy(latest.content)
        changed = False
        for section in SECTIONS:
            for st in content[section]:
                if data.line_no in st["source_lines"]:
                    new_text, did = replace_phrase(st["text"], data.original, data.confirmed)
                    if did:
                        st["text"] = new_text
                        changed = True
        if changed:
            latest = models.NoteVersion(
                consultation_id=consultation.id,
                version=latest.version + 1,
                content=content,
                saved_by=doctor.id,
                reason="edited",
            )
            consultation.status = "edited"
            db.add(latest)

    db.commit()

    # 3. The agent learns: the same garble is fixed automatically next time
    memory = load_memory()
    memory[normalize(data.original)] = data.confirmed
    save_memory(memory)
    append_log(
        [{
            **entry,
            "consultation": consultation.id,
            "line_id": data.line_no,
            "doctor_id": doctor.id,
            "time": datetime.now().isoformat(timespec="seconds"),
        }],
        "data/correction_log_live.json",
    )

    log_action(db, doctor.id, "correction_confirmed", consultation.id,
               f"line {data.line_no}, {entry['status']}")
    if latest is None:
        raise HTTPException(status_code=404, detail="No note yet")
    db.refresh(latest)
    return note_out(consultation, latest)