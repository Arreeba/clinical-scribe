from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import get_current_doctor, get_owned_consultation, log_action
from app.database import get_db
from app.note_schema import Note
from app.routers.notes import latest_version
from app.services.summary import generate_summary

router = APIRouter(prefix="/api/consultations", tags=["summary"])


def latest_summary(db, consultation_id):
    return (
        db.query(models.Summary)
        .filter_by(consultation_id=consultation_id)
        .order_by(models.Summary.id.desc())
        .first()
    )


def summary_out(row):
    return schemas.SummaryOut(
        consultation_id=row.consultation_id, text=row.text, created_at=row.created_at
    )


@router.post("/{consultation_id}/summary", response_model=schemas.SummaryOut)
def create_summary(
    consultation_id: int,
    db: Session = Depends(get_db),
    doctor: models.Doctor = Depends(get_current_doctor),
):
    consultation = get_owned_consultation(db, consultation_id, doctor)

    # The rule: a summary is only made from an approved note
    if consultation.status != "approved":
        log_action(db, doctor.id, "summary_refused_not_approved", consultation.id,
                   f"status is {consultation.status}")
        raise HTTPException(status_code=409, detail="The summary can only be created from an approved note")

    # Already made? Return it. The approved note can never change, so neither can the summary.
    existing = latest_summary(db, consultation.id)
    if existing is not None:
        log_action(db, doctor.id, "summary_viewed", consultation.id)
        return summary_out(existing)

    latest = latest_version(db, consultation.id)
    try:
        text, problems, tokens = generate_summary(Note(**latest.content))
    except Exception as error:
        log_action(db, doctor.id, "summary_failed", consultation.id, str(error)[:200])
        raise HTTPException(status_code=502, detail="Could not create the summary. Nothing was saved.")

    if problems:
        log_action(db, doctor.id, "summary_failed_checks", consultation.id, f"{len(problems)} problems left")
        raise HTTPException(
            status_code=502,
            detail="The summary did not pass the safety checks, so it was not saved. Please try again.",
        )

    row = models.Summary(consultation_id=consultation.id, text=text)
    db.add(row)
    db.commit()
    db.refresh(row)
    log_action(db, doctor.id, "summary_created", consultation.id, f"tokens {tokens}")
    return summary_out(row)


@router.get("/{consultation_id}/summary", response_model=schemas.SummaryOut)
def get_summary(
    consultation_id: int,
    db: Session = Depends(get_db),
    doctor: models.Doctor = Depends(get_current_doctor),
):
    consultation = get_owned_consultation(db, consultation_id, doctor)
    row = latest_summary(db, consultation.id)
    if row is None:
        raise HTTPException(status_code=404, detail="No summary yet")
    log_action(db, doctor.id, "summary_viewed", consultation.id)
    return summary_out(row)