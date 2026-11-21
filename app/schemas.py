from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConsultationCreate(BaseModel):
    patient_name: str


class ConsultationOut(BaseModel):
    id: int
    patient_name: str
    status: str
    consent_given: bool
    created_at: datetime


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    time: datetime
    doctor_id: int | None
    action: str
    consultation_id: int | None
    detail: str

class TranscriptLineOut(BaseModel):
    line_no: int
    speaker: str
    text: str
    original: str
    corrections: list
    words: list = []
    low_words: list = []


class NoteOut(BaseModel):
    consultation_id: int
    status: str
    version: int
    reason: str
    note: dict    

class CorrectionConfirm(BaseModel):
    line_no: int
    original: str
    confirmed: str


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version: int
    reason: str
    saved_by: int | None
    created_at: datetime    

class SummaryOut(BaseModel):
    consultation_id: int
    text: str
    created_at: datetime    