import os
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app import models
from app.database import get_db

load_dotenv()
JWT_SECRET = os.environ["JWT_SECRET"]
TOKEN_HOURS = 8

# Tells Swagger where the login is, so it shows an "Authorize" button
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")


def create_token(doctor_id):
    payload = {
        "sub": str(doctor_id),
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def log_action(db, doctor_id, action, consultation_id=None, detail=""):
    # Adds one row to the audit log. Nothing ever edits or deletes these rows.
    db.add(models.AuditLog(
        doctor_id=doctor_id,
        action=action,
        consultation_id=consultation_id,
        detail=detail,
    ))
    db.commit()


def get_current_doctor(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    # Runs before every protected endpoint: who is this badge for?
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        doctor = db.get(models.Doctor, int(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if doctor is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return doctor


def get_owned_consultation(db, consultation_id, doctor):
    # Finds a consultation, and refuses unless it belongs to this doctor
    consultation = db.get(models.Consultation, consultation_id)
    if consultation is None:
        raise HTTPException(status_code=404, detail="Consultation not found")
    if consultation.doctor_id != doctor.id:
        log_action(db, doctor.id, "access_denied", consultation_id, "not the treating doctor")
        raise HTTPException(status_code=403, detail="This consultation belongs to another doctor")
    return consultation