from app import models
from app.database import Base, SessionLocal, engine

Base.metadata.create_all(bind=engine)

# Real addresses are typed in here, so they never appear in the code or in a chat
my_name = input("Your name: ").strip()
my_email = input("Your first Gmail (the one that signs in with Google): ").strip().lower()
guide_name = input("Your guide's name: ").strip()
guide_email = input("Your guide's Google email: ").strip().lower()

for email in (my_email, guide_email):
    if "@" not in email:
        raise SystemExit("That does not look like an email address. Nothing was changed.")

# (name, email, specialty, licence number). Licence numbers are made up.
ROSTER = [
    (my_name, my_email, "Dermatology", "DERM-0001"),
    (guide_name, guide_email, "Dermatology", "DERM-0002"),
    ("Dr. Layla Hassan", "layla.hassan@clinic.example", "Dermatology", "DERM-0003"),
    ("Dr. Omar Nasser", "omar.nasser@clinic.example", "Dermatology", "DERM-0004"),
    ("Dr. Salma Karim", "salma.karim@clinic.example", "Dermatology", "DERM-0005"),
]

db = SessionLocal()
added = 0
for name, email, specialty, licence in ROSTER:
    if db.query(models.DoctorRegistry).filter_by(email=email).first():
        continue   # already there, so running this twice does no harm
    db.add(models.DoctorRegistry(full_name=name, email=email, specialty=specialty,
                                 licence_number=licence, active=True))
    added += 1
db.commit()

print(f"\nAdded {added} roster entries. The registry now holds:")
for r in db.query(models.DoctorRegistry).order_by(models.DoctorRegistry.id):
    print(f"  {r.licence_number}  {r.full_name:22} {r.email}  active={r.active}")