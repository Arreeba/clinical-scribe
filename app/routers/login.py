from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models
from app.auth import create_token, log_action
from app.database import get_db
from app.security import verify_password

router = APIRouter(prefix="/api", tags=["login"])


@router.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    who = form.username.strip().lower()
    if "@" in who:
        doctor = db.query(models.Doctor).filter(func.lower(models.Doctor.email) == who).first()
    else:
        doctor = db.query(models.Doctor).filter(func.lower(models.Doctor.username) == who).first()

    if doctor is None or not verify_password(form.password, doctor.password_hash):
        log_action(db, doctor.id if doctor else None, "login_failed", detail="failed login attempt")
        raise HTTPException(status_code=401, detail="Wrong username or password")
    log_action(db, doctor.id, "login")
    return {"access_token": create_token(doctor.id), "token_type": "bearer"}