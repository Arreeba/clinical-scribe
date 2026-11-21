# Clinical Scribe

An AI tool that listens to a mock doctor-patient consultation, drafts a structured clinical note, and prepares a plain-language patient summary. The doctor reviews and approves everything. The tool never diagnoses. All data is fictional.

## Pipeline

Audio -> Whisper (speech to text) -> medicine-name correction agent -> note generator (Groq) -> doctor review and approval -> patient summary and PDF.

## Setup

1. Python 3.12. Create a virtual environment and install the requirements:
   `pip install -r requirements.txt`
2. PyTorch. With an NVIDIA GPU:
   `pip install torch --index-url https://download.pytorch.org/whl/cu128`
   Without a GPU, install the CPU build from pytorch.org (Whisper will be slower).
3. Install ffmpeg (needed to read audio files).
4. Copy `.env.example` to `.env` and fill in every value. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` if Google sign-up is needed.
5. Create the tables and the demo data:
   `python init_db.py`, then `python seed_registry.py`, then `python set_password.py dr_amina` and `python set_password.py dr_omar`.

## Run (from the project's root folder, in two terminals)

- Backend: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- Screen: `streamlit run screen/app.py`

## Notes

- Never commit `.env` or `secrets.toml`. `DATA_KEY` must stay the same wherever the database is used, or encrypted data becomes unreadable.
- The microphone in the browser only works on `localhost` or over HTTPS.