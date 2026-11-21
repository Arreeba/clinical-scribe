from sqlalchemy import text

from app import models
from app.database import SessionLocal, engine

db = SessionLocal()
patient = models.Patient(name="Fictional Patient One")
db.add(patient)
db.commit()
db.refresh(patient)

with engine.connect() as connection:
    raw = connection.execute(
        text("SELECT name FROM patients WHERE id = :i"), {"i": patient.id}
    ).scalar()

print("Database:", engine.dialect.name)
print("Stored in the database:", raw[:70], "...")
print("Read back through the app:", patient.name)

db.delete(patient)   # clean up the test row
db.commit()