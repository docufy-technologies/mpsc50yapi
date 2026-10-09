"""Create (or promote) an admin account.

Usage:  python -m scripts.create_admin admin@example.com StrongPassword123
"""
import sys

from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.models import User
from app.security import hash_password

if len(sys.argv) != 3:
    sys.exit("Usage: python -m scripts.create_admin <email> <password>")

email, password = sys.argv[1].lower(), sys.argv[2]
Base.metadata.create_all(bind=engine)

with SessionLocal() as db:
    user = db.scalar(select(User).where(User.email == email))
    if user:
        user.is_admin = True
    else:
        db.add(User(email=email, password_hash=hash_password(password), is_admin=True))
    db.commit()
print(f"Admin ready: {email}")
