from sqlmodel import SQLModel, select
from sqlmodel import Session

from app.database import engine
from app.models import Admin

EMAIL = "admin@example.com"
PASSWORD_HASH = "replace-with-argon2id-hash"

SQLModel.metadata.create_all(bind=engine)

with Session(bind=engine) as session:
    if session.scalar(select(Admin).where(Admin.email == EMAIL)):
        raise SystemExit(f"Admin {EMAIL} already exists")
    session.add(Admin(email=EMAIL, password_hash=PASSWORD_HASH))
    session.commit()

print(f"Admin {EMAIL} created")
