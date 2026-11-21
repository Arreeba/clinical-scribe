from sqlalchemy import text

from app.database import engine

with engine.connect() as connection:
    print("Database:", engine.dialect.name)
    print("Connected as:", connection.execute(text("SELECT current_user")).scalar())
    print("Server version:", connection.execute(text("SELECT version()")).scalar()[:60])
    print("Timezone:", connection.execute(text("SHOW timezone")).scalar())