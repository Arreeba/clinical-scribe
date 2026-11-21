import json
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.database import Base
from app.security import decrypt_text, encrypt_text


def now():
    return datetime.now(timezone.utc)


class EncryptedText(TypeDecorator):
    # A text column that is scrambled on the way into the database
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else encrypt_text(value)

    def process_result_value(self, value, dialect):
        return None if value is None else decrypt_text(value)


class EncryptedJSON(TypeDecorator):
    # Same idea for lists and dictionaries (notes, word scores)
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else encrypt_text(json.dumps(value))

    def process_result_value(self, value, dialect):
        return None if value is None else json.loads(decrypt_text(value))


class DoctorRegistry(Base):
    # The clinic's roster of doctors who are allowed to create an account
    __tablename__ = "doctor_registry"
    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(200), unique=True)
    specialty: Mapped[str] = mapped_column(String(50))
    licence_number: Mapped[str] = mapped_column(String(30), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Doctor(Base):
    # An account that can log in
    __tablename__ = "doctors"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    display_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(200), unique=True, nullable=True)
    registry_id: Mapped[int] = mapped_column(ForeignKey("doctor_registry.id"), unique=True, nullable=True)


class Patient(Base):
    __tablename__ = "patients"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(EncryptedText)


class Consultation(Base):
    __tablename__ = "consultations"
    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"))
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Consent(Base):
    __tablename__ = "consents"
    id: Mapped[int] = mapped_column(primary_key=True)
    consultation_id: Mapped[int] = mapped_column(ForeignKey("consultations.id"))
    recorded_by: Mapped[int] = mapped_column(ForeignKey("doctors.id"))
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class TranscriptLine(Base):
    __tablename__ = "transcript_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    consultation_id: Mapped[int] = mapped_column(ForeignKey("consultations.id"))
    line_no: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[str] = mapped_column(String(10))
    text: Mapped[str] = mapped_column(EncryptedText)
    original: Mapped[str] = mapped_column(EncryptedText)   # what Whisper heard
    words: Mapped[list] = mapped_column(EncryptedJSON, default=list)   # words with scores
    corrections: Mapped[list] = mapped_column(EncryptedJSON, default=list)   # agent fixes and suggestions


class NoteVersion(Base):
    __tablename__ = "note_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    consultation_id: Mapped[int] = mapped_column(ForeignKey("consultations.id"))
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict] = mapped_column(EncryptedJSON)   # the whole note as one snapshot
    saved_by: Mapped[int] = mapped_column(ForeignKey("doctors.id"), nullable=True)
    reason: Mapped[str] = mapped_column(String(20))   # generated, edited or approved
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Summary(Base):
    __tablename__ = "summaries"
    id: Mapped[int] = mapped_column(primary_key=True)
    consultation_id: Mapped[int] = mapped_column(ForeignKey("consultations.id"))
    text: Mapped[str] = mapped_column(EncryptedText)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class AuditLog(Base):
    # Rows are only ever added. No code updates or deletes them.
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    time: Mapped[datetime] = mapped_column(DateTime, default=now)
    doctor_id: Mapped[int] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(50))
    consultation_id: Mapped[int] = mapped_column(Integer, nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="")