from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import get_current_doctor, get_owned_consultation, log_action
from app.database import get_db

router = APIRouter(prefix="/api/consultations", tags=["consultations"])


def to_out(db, consultation):
    patient = db.get(models.Patient, consultation.patient_id)
    consent = db.query(models.Consent).filter_by(consultation_id=consultation.id).first()
    return schemas.ConsultationOut(
        id=consultation.id,
        patient_name=patient.name,
        status=consultation.status,
        consent_given=consent is not None,
        created_at=consultation.created_at,
    )


@router.post("", response_model=schemas.ConsultationOut)
def create_consultation(
    data: schemas.ConsultationCreate,
    db: Session = Depends(get_db),
    doctor: models.Doctor = Depends(get_current_doctor),
):
    patient = models.Patient(name=data.patient_name)
    db.add(patient)
    db.flush()   # gives the patient an ID without finishing the save
    consultation = models.Consultation(doctor_id=doctor.id, patient_id=patient.id)
    db.add(consultation)
    db.commit()
    db.refresh(consultation)
    log_action(db, doctor.id, "consultation_created", consultation.id)
    return to_out(db, consultation)


@router.get("", response_model=list[schemas.ConsultationOut])
def list_consultations(
    db: Session = Depends(get_db),
    doctor: models.Doctor = Depends(get_current_doctor),
):
    mine = db.query(models.Consultation).filter_by(doctor_id=doctor.id).all()
    log_action(db, doctor.id, "consultations_listed")
    return [to_out(db, c) for c in mine]


@router.get("/{consultation_id}", response_model=schemas.ConsultationOut)
def get_consultation(
    consultation_id: int,
    db: Session = Depends(get_db),
    doctor: models.Doctor = Depends(get_current_doctor),
):
    consultation = get_owned_consultation(db, consultation_id, doctor)
    log_action(db, doctor.id, "consultation_viewed", consultation.id)
    return to_out(db, consultation)


@router.post("/{consultation_id}/consent", response_model=schemas.ConsultationOut)
def record_consent(
    consultation_id: int,
    db: Session = Depends(get_db),
    doctor: models.Doctor = Depends(get_current_doctor),
):
    consultation = get_owned_consultation(db, consultation_id, doctor)
    existing = db.query(models.Consent).filter_by(consultation_id=consultation.id).first()
    if existing is None:
        db.add(models.Consent(consultation_id=consultation.id, recorded_by=doctor.id))
        db.commit()
        log_action(db, doctor.id, "consent_recorded", consultation.id)
    return to_out(db, consultation)


@router.get("/{consultation_id}/audit", response_model=list[schemas.AuditOut])
def consultation_audit(
    consultation_id: int,
    db: Session = Depends(get_db),
    doctor: models.Doctor = Depends(get_current_doctor),
):
    consultation = get_owned_consultation(db, consultation_id, doctor)
    return (
        db.query(models.AuditLog)
        .filter_by(consultation_id=consultation.id)
        .order_by(models.AuditLog.id)
        .all()
    )