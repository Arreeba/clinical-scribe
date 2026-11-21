import hashlib
import os
import re
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.auth import log_action
from app.database import get_db
from app.security import hash_password

router = APIRouter(prefix="/api/signup", tags=["signup"])

USERNAME_RULE = re.compile(r"^[a-z][a-z0-9_]{2,29}$")


class SignupCheck(BaseModel):
    email: str = Field(max_length=200)
    email_verified: bool


class SignupComplete(SignupCheck):
    username: str = Field(max_length=50)
    password: str = Field(max_length=200)


def require_key(db, key):
    # Only the Streamlit app, which holds the key, may call these endpoints
    expected = os.environ.get("SIGNUP_KEY", "")
    if not expected:
        raise HTTPException(status_code=503, detail="Sign-up is not configured on this server")
    if not key or not secrets.compare_digest(key.encode(), expected.encode()):
        log_action(db, None, "signup_bad_key")
        raise HTTPException(status_code=401, detail="Invalid sign-up key")


def fingerprint(email):
    # A short code instead of the address, so the audit log does not store an outsider's email
    return hashlib.sha256(email.encode()).hexdigest()[:10]


def find_registry_entry(db, email, email_verified):
    # The rules that decide whether this person may sign up
    email = email.strip().lower()
    tag = fingerprint(email)
    if not email_verified:
        log_action(db, None, "signup_refused_unverified_email", detail=f"email {tag}")
        raise HTTPException(status_code=403, detail="Google did not verify this email address")

    entry = db.query(models.DoctorRegistry).filter_by(email=email).first()
    if entry is None:
        log_action(db, None, "signup_refused_not_registered", detail=f"email {tag}")
        raise HTTPException(status_code=403, detail="This email is not registered with the clinic")
    if not entry.active:
        log_action(db, None, "signup_refused_inactive", detail=f"registry {entry.id}")
        raise HTTPException(status_code=403, detail="This registry entry is not active")

    exists = db.query(models.Doctor).filter(
        (models.Doctor.registry_id == entry.id) | (models.Doctor.email == email)
    ).first()
    if exists:
        log_action(db, None, "signup_refused_already_registered", detail=f"registry {entry.id}")
        raise HTTPException(status_code=409, detail="An account already exists for this email. Please log in.")
    return entry, email


@router.post("/check")
def check(
    data: SignupCheck,
    db: Session = Depends(get_db),
    x_signup_key: str | None = Header(default=None, alias="X-Signup-Key"),
):
    require_key(db, x_signup_key)
    entry, _ = find_registry_entry(db, data.email, data.email_verified)
    log_action(db, None, "signup_check_passed", detail=f"registry {entry.id}")
    return {"full_name": entry.full_name, "specialty": entry.specialty}


@router.post("/complete")
def complete(
    data: SignupComplete,
    db: Session = Depends(get_db),
    x_signup_key: str | None = Header(default=None, alias="X-Signup-Key"),
):
    require_key(db, x_signup_key)
    # The checks run again here, so the earlier check is never simply trusted
    entry, email = find_registry_entry(db, data.email, data.email_verified)

    username = data.username.strip().lower()
    if not USERNAME_RULE.match(username):
        raise HTTPException(
            status_code=422,
            detail="Username must be 3 to 30 characters: lowercase letters, digits or underscores, "
                   "starting with a letter",
        )
    if db.query(models.Doctor).filter(func.lower(models.Doctor.username) == username).first():
        log_action(db, None, "signup_refused_username_taken", detail=f"registry {entry.id}")
        raise HTTPException(status_code=409, detail="That username is already taken")

    password = data.password
    if len(password) < 8 or len(password.encode("utf-8")) > 72:
        raise HTTPException(status_code=422, detail="The password must be 8 to 72 characters")
    if password.lower() == username:
        raise HTTPException(status_code=422, detail="The password must not be the same as the username")

    doctor = models.Doctor(
        username=username,
        password_hash=hash_password(password),
        display_name=entry.full_name,
        email=email,
        registry_id=entry.id,
    )
    db.add(doctor)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account already exists for this email or username")
    db.refresh(doctor)
    log_action(db, doctor.id, "signup_completed", detail=f"registry {entry.id}")
    return {"username": doctor.username, "display_name": doctor.display_name}