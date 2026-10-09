# 50 Years Alumni Event: Backend API (FastAPI)

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # Windows: copy .env.example .env
fastapi dev app/main.py          # or: uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000/docs for the interactive API page.

## Create an admin
```bash
python -m scripts.create_admin admin@example.com YourStrongPassword
```

## Run tests
```bash
pytest -v
```

## Endpoints
| Method | Path | Who | What |
|---|---|---|---|
| POST | /auth/signup | anyone | create alumni account + profile |
| POST | /auth/login | anyone | get access token (send email as `username`) |
| GET | /auth/me | logged in | current user + profile |
| GET | /events/ | anyone | list events |
| POST | /events/ | admin | create event |
| POST | /registrations | logged in | register (with guests) |
| GET | /registrations/me | logged in | my registrations |
| POST | /registrations/{id}/cancel | logged in | cancel mine |
| GET | /admin/registrations | admin | all registrations (`?event_id=`) |
| PATCH | /admin/registrations/{id}/payment | admin | mark payment, confirms registration |
