import secrets

from app import models
from app.database import Base, SessionLocal, engine
from app.security import hash_password

Base.metadata.create_all(bind=engine)

# Two demo doctors, to show that one cannot open the other's consultations.
# No password is written here. Set real ones with set_password.py.
DEMO_DOCTORS = [
    ("dr_amina", "Dr. Amina (demo)"),
    ("dr_omar", "Dr. Omar (demo)"),
]

db = SessionLocal()
for username, display_name in DEMO_DOCTORS:
    if not db.query(models.Doctor).filter_by(username=username).first():
        db.add(models.Doctor(
            username=username,
            display_name=display_name,
            # A random password that nobody knows, so the account cannot be used
            # until you run set_password.py
            password_hash=hash_password(secrets.token_urlsafe(32)),
        ))
db.commit()
print("Database ready. Demo doctors:", [d.username for d in db.query(models.Doctor).all()])

