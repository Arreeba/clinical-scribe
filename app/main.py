from fastapi import FastAPI

from app import models  # noqa: registers all the tables
from app.database import Base, engine
from app.routers import audio, consultations, export, login, notes, signup, summary

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Clinical Scribe")
app.include_router(login.router)
app.include_router(consultations.router)
app.include_router(audio.router)
app.include_router(notes.router)
app.include_router(summary.router)
app.include_router(export.router)
app.include_router(signup.router)

@app.get("/")
def home():
    return {"message": "Hello, the API is running"}