import os

import requests
from dotenv import load_dotenv

load_dotenv()   # reads SIGNUP_KEY from your .env file

BASE_URL = os.environ.get("API_URL", "http://localhost:8000")
SIGNUP_KEY = os.environ.get("SIGNUP_KEY", "")


def call(method, path, token=None, **kwargs):
    # Sends one request to the server. Returns (data, error message, status code).
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    headers.update(kwargs.pop("headers", {}))   # lets a caller add its own headers
    timeout = kwargs.pop("timeout", 30)
    try:
        response = requests.request(method, BASE_URL + path, headers=headers, timeout=timeout, **kwargs)
    except requests.exceptions.RequestException:
        return None, "Cannot reach the server. Is uvicorn running?", 0
    if response.ok:
        return response.json(), None, response.status_code
    try:
        detail = response.json().get("detail", response.text)
    except ValueError:
        detail = response.text
    return None, str(detail), response.status_code


def login(username, password):
    # The login endpoint expects a form, not JSON
    return call("POST", "/api/login", data={"username": username, "password": password})


def list_consultations(token):
    return call("GET", "/api/consultations", token)


def create_consultation(token, patient_name):
    return call("POST", "/api/consultations", token, json={"patient_name": patient_name})


def record_consent(token, consultation_id):
    return call("POST", f"/api/consultations/{consultation_id}/consent", token)


def upload_audio(token, consultation_id, doctor_file, patient_file):
    # Works for both uploaded files and microphone recordings
    def part(clip, default_name):
        name = getattr(clip, "name", None) or default_name
        kind = getattr(clip, "type", None) or "application/octet-stream"
        return (name, clip.getvalue(), kind)

    files = {
        "doctor_audio": part(doctor_file, "doctor.wav"),
        "patient_audio": part(patient_file, "patient.wav"),
    }
    # Whisper and the note generator take a minute or two, so wait up to 5 minutes
    return call("POST", f"/api/consultations/{consultation_id}/audio", token, files=files, timeout=300)


def get_transcript(token, consultation_id):
    return call("GET", f"/api/consultations/{consultation_id}/transcript", token)


def get_note(token, consultation_id):
    return call("GET", f"/api/consultations/{consultation_id}/note", token)

def edit_note(token, consultation_id, note):
    return call("PUT", f"/api/consultations/{consultation_id}/note", token, json=note)


def approve_note(token, consultation_id):
    return call("PUT", f"/api/consultations/{consultation_id}/approve", token)


def confirm_correction(token, consultation_id, line_no, original, confirmed):
    return call(
        "POST", f"/api/consultations/{consultation_id}/corrections", token,
        json={"line_no": line_no, "original": original, "confirmed": confirmed},
    )

def create_summary(token, consultation_id):
    # Takes a few seconds: the language model writes it, then the checks run
    return call("POST", f"/api/consultations/{consultation_id}/summary", token, timeout=120)


def get_summary(token, consultation_id):
    return call("GET", f"/api/consultations/{consultation_id}/summary", token)


def get_versions(token, consultation_id):
    return call("GET", f"/api/consultations/{consultation_id}/versions", token)


def get_audit(token, consultation_id):
    return call("GET", f"/api/consultations/{consultation_id}/audit", token)


def get_pdf(token, consultation_id):
    # The PDF comes back as raw bytes, not JSON, so it has its own function
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.get(
            BASE_URL + f"/api/consultations/{consultation_id}/pdf", headers=headers, timeout=60
        )
    except requests.exceptions.RequestException:
        return None, "Cannot reach the server. Is uvicorn running?", 0
    if response.ok:
        return response.content, None, response.status_code
    try:
        detail = response.json().get("detail", response.text)
    except ValueError:
        detail = response.text
    return None, str(detail), response.status_code

def signup_check(email, email_verified):
    return call("POST", "/api/signup/check",
                json={"email": email, "email_verified": email_verified},
                headers={"X-Signup-Key": SIGNUP_KEY})


def signup_complete(email, email_verified, username, password):
    return call("POST", "/api/signup/complete",
                json={"email": email, "email_verified": email_verified,
                      "username": username, "password": password},
                headers={"X-Signup-Key": SIGNUP_KEY})