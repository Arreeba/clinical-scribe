import getpass
import sys

from app import models
from app.database import SessionLocal
from app.security import hash_password

# Usage: python set_password.py dr_amina
username = sys.argv[1] if len(sys.argv) > 1 else input("Username: ")
password = getpass.getpass("New password (typing is hidden): ")
again = getpass.getpass("Type it again: ")

if password != again:
    print("The two passwords do not match. Nothing changed.")
    sys.exit(1)
if len(password) < 8:
    print("Use at least 8 characters. Nothing changed.")
    sys.exit(1)

db = SessionLocal()
doctor = db.query(models.Doctor).filter_by(username=username).first()
if doctor is None:
    print("No doctor with that username.")
    sys.exit(1)

doctor.password_hash = hash_password(password)
db.commit()
print(f"Password changed for {username}.")