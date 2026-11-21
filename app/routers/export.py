import io
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Response
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from sqlalchemy.orm import Session

from app import models
from app.auth import get_current_doctor, get_owned_consultation, log_action
from app.database import get_db
from app.routers.notes import latest_version
from app.routers.summary import latest_summary

router = APIRouter(prefix="/api/consultations", tags=["export"])

# The standard PDF font cannot draw some special characters, so swap them for plain ones
REPLACEMENTS = {
    "\u2011": "-", "\u2013": "-", "\u2014": "-",
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
}


def clean(text):
    for old, new in REPLACEMENTS.items():
        text = text.replace(old, new)
    return escape(text)


def build_pdf(consultation, patient_name, doctor_name, approved_at, summary_text):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
        title="Visit summary",
    )
    base = getSampleStyleSheet()
    normal = ParagraphStyle("normal", parent=base["Normal"], fontSize=11, leading=15)
    title = base["Title"]
    heading = ParagraphStyle("heading", parent=base["Heading2"], spaceBefore=14, spaceAfter=4)
    bullet = ParagraphStyle("bullet", parent=normal, leftIndent=14, bulletIndent=2, spaceAfter=4)
    small = ParagraphStyle("small", parent=base["Normal"], fontSize=8, textColor=colors.HexColor("#666666"))

    story = [Paragraph("Your visit summary", title)]
    story.append(Paragraph(f"<b>Patient:</b> {clean(patient_name)}", normal))
    story.append(Paragraph(f"<b>Doctor:</b> {clean(doctor_name)}", normal))
    story.append(Paragraph(f"<b>Date:</b> {approved_at:%d %B %Y}", normal))
    story.append(Spacer(1, 6))

    # The summary text is built from blocks: a heading line, then sentences or "- " items
    for block in summary_text.split("\n\n"):
        lines = block.split("\n")
        if len(lines) > 1 and not lines[0].startswith("- "):
            story.append(Paragraph(clean(lines[0]), heading))
            lines = lines[1:]
        for line in lines:
            if line.startswith("- "):
                story.append(Paragraph(clean(line[2:]), bullet, bulletText="\u2022"))
            else:
                story.append(Paragraph(clean(line), normal))
        story.append(Spacer(1, 4))

    story.append(Spacer(1, 16))
    story.append(Paragraph("Fictional demonstration data. Not for clinical use.", small))

    doc.build(story)
    return buffer.getvalue()


@router.get("/{consultation_id}/pdf")
def export_pdf(
    consultation_id: int,
    db: Session = Depends(get_db),
    doctor: models.Doctor = Depends(get_current_doctor),
):
    consultation = get_owned_consultation(db, consultation_id, doctor)

    # Rule 1: only an approved note can be exported
    if consultation.status != "approved":
        log_action(db, doctor.id, "pdf_refused_not_approved", consultation.id,
                   f"status is {consultation.status}")
        raise HTTPException(status_code=409, detail="Only an approved note can be exported")

    # Rule 2: the PDF is the patient summary, so it must exist already
    summary = latest_summary(db, consultation.id)
    if summary is None:
        log_action(db, doctor.id, "pdf_refused_no_summary", consultation.id)
        raise HTTPException(status_code=409, detail="Create the patient summary first")

    latest = latest_version(db, consultation.id)
    patient = db.get(models.Patient, consultation.patient_id)
    approver = db.get(models.Doctor, latest.saved_by) if latest.saved_by else doctor

    pdf = build_pdf(consultation, patient.name, approver.display_name, latest.created_at, summary.text)
    log_action(db, doctor.id, "pdf_exported", consultation.id, f"summary pdf, note version {latest.version}")
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="visit_summary_{consultation.id}.pdf"'},
    )