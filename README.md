# Clinical Scribe

An AI tool that listens to a mock doctor-patient consultation, drafts a structured clinical note, and prepares a plain-language summary for the patient. The doctor reviews, edits and approves everything. The tool never diagnoses. **All data in this project is fictional, and the medical content has not been clinically validated. It is not for clinical use.**

## What it does

1. The doctor logs in, creates a consultation, and records the patient's consent (a popup).
2. The doctor's part and the patient's part are recorded separately (microphone or audio files). Recording them separately means every transcript line has a reliable speaker label.
3. **Whisper** (small model) turns the audio into text. Each word keeps a confidence score.
4. A **correction agent** looks for misheard medicine names, suggests names from an FDA-derived vocabulary, and remembers fixes that a doctor has confirmed.
5. A **note generator** (Groq, gpt-oss-120b) writes a note with four sections (complaint, history, assessment, plan). Every statement cites the transcript lines it came from.
6. The doctor sees the transcript and the note side by side. Statements about medicines or doses, words the language model found unclear, and statements built on words Whisper scored below 0.6 are flagged. The doctor ticks each flag as reviewed, edits where needed, and approves.
7. Approval locks the note on the server. Every edit before that is saved as a new version.
8. A plain-language **patient summary** is written from the approved note only and can be downloaded as a PDF.

The assistant never diagnoses: the assessment section stays empty unless the doctor states an assessment aloud, and the summary is checked so that it adds no numbers, medicine names or diagnosis-style wording that are not in the note.

## Architecture

| Part | Technology |
|---|---|
| Screen | Streamlit (`screen/`) |
| Backend | FastAPI (`app/`) |
| Database | PostgreSQL through SQLAlchemy (SQLite is used if `DATABASE_URL` is not set) |
| Speech to text | OpenAI Whisper, small model |
| Note and summary | Groq API, `openai/gpt-oss-120b`, with strict JSON schemas and checks in code |
| Medicine-name vocabulary | Generic names derived from the openFDA drug label data |

## Security

- Patient names, transcripts, notes and summaries are encrypted in the database by the application (`DATA_KEY`).
- Passwords are stored only as hashes. Logins use signed tokens that expire.
- A consultation can only be opened by the doctor who owns it.
- The server refuses audio unless consent is recorded.
- The audit log records logins, views, edits, approvals, exports and refused attempts, and nothing in the code updates or deletes its rows.
- Audio is processed from a temporary file that is deleted straight after transcription. It is not stored.
- Sign-up is limited to doctors on a registry table. Google confirms the email, then the doctor chooses a username and password. The screen calls the sign-up endpoints with a shared key (`SIGNUP_KEY`).
- Not covered: encryption in transit on a plain HTTP deployment, encrypted audio storage (audio is not stored), limits on failed logins, and password reset by email.

## Evaluation (small, fictional data)

Ten scripted dermatology consultations, each with a checklist of key facts. Eight were used while developing and two (scripts 5 and 9) were held out and run once with everything frozen.

| | Development (8 scripts) | Held-out (2 scripts) |
|---|---|---|
| Checklist facts captured | 57 of 58 | 13 of 14 |
| Invented statements | 0 | 0 |
| False flags | 0 | 0 |
| Medicine names misheard by Whisper | 4 of 8 | 1 of 2 |

These counts were made by hand. With so few scripts, treat them as an initial check and not as a measure of accuracy. Ordinary words that Whisper mishears into another sensible word are often not caught, and the doctor's review is the safeguard. The results are in `data/` (notes, transcripts and the held-out results), and `frozen/` holds the code and settings as they were when the held-out test ran.

## Setup

1. Python 3.12. Create a virtual environment and install the requirements:
   `pip install -r requirements.txt`
2. PyTorch. With an NVIDIA GPU:
   `pip install torch --index-url https://download.pytorch.org/whl/cu128`
   Without a GPU, install the CPU build from pytorch.org. Whisper will be slower.
3. Install ffmpeg (needed to read audio files), for example `sudo apt install ffmpeg` on Ubuntu.
4. Copy `.env.example` to `.env` and fill in every value:

   | Setting | What it is |
   |---|---|
   | `DATABASE_URL` | `postgresql+psycopg2://USER:PASSWORD@HOST:5432/DATABASE_NAME` (special characters in the password must be URL-encoded) |
   | `DATA_KEY` | Encrypts the sensitive columns. It must stay the same wherever the database is used, or encrypted data becomes unreadable |
   | `JWT_SECRET` | Signs login tokens |
   | `SIGNUP_KEY` | Shared between the screen and the backend for sign-up |
   | `GROQ_API_KEY` | Lets the backend call Groq |

5. For Google sign-up, copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill it in. The `redirect_uri` must be the exact address of the screen followed by `/oauth2callback`, and the same address must be added in the Google Cloud console. Without it, logging in with a username and password still works.
6. Create the tables and the demo data (run once, from the project's root folder):

   ```
   python init_db.py
   python seed_registry.py
   python set_password.py dr_amina
   python set_password.py dr_omar
   ```

   `seed_registry.py` asks for the real email addresses of the people who will sign up, so none are stored in the code.

## Run (from the project's root folder, in two terminals)

- Backend: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- Screen: `streamlit run screen/app.py` (set `API_URL` if the backend is not at `http://localhost:8000`)

The microphone in the browser only works on `localhost` or over HTTPS. Uploading audio files works either way. The first request after the backend starts is slow, because Whisper loads.

## Folders

- `app/`: the backend (routes, services, models, security)
- `screen/`: the Streamlit screen
- `scripts/`: the ten fictional consultation scripts and their checklists
- `data/`: settings, the drug vocabulary, the agent's saved fixes, and the evaluation results
- `frozen/`: the code and settings as they were for the held-out test
- Root: setup and evaluation tools (`init_db.py`, `seed_registry.py`, `set_password.py`, `transcribe_all.py`, `review_corrections.py`, `run_dev_notes.py`, `check_scripts.py`)

## Limitations

- Whisper's output varies from run to run, so the figures come from one saved set of transcripts.
- The correction agent only fixes medicine names, and it remembers exact phrases only.
- Speaker labels come from recording the two speakers separately, not from the voice.
- The summary repeats whatever the doctor approves, including a misheard word that was not corrected.
- Translation of the summary and automatic PDF of the clinical note are not implemented.
