# GateReady (SDE Portfolio)

Phase 1 scaffolding: FastAPI + LangGraph hello graph.

## Backend

Create a virtual environment, then install deps:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

Run the API:

```powershell
uvicorn app.main:app --reload --app-dir backend
```

Create a `.env` file in `backend/` with:

```
MONGODB_URI=mongodb+srv://<user>:<password>@cluster0.gku8jay.mongodb.net/
MONGODB_DB_NAME=booking_assistant
MONGODB_BOOKINGS_COLLECTION=bookings
MONGODB_USERS_COLLECTION=users
MONGODB_FLIGHT_INFO_COLLECTION=flight_info
API_BASE_URL=http://127.0.0.1:8000
GROQ_API_KEY=your_key_here
GROQ_MODEL=llama-3.1-8b-instant
JWT_SECRET=dev-secret
JWT_REFRESH_SECRET=dev-refresh-secret
ACCESS_TOKEN_TTL_MINUTES=15
REFRESH_TOKEN_TTL_DAYS=7
CHECKPOINT_DB=backend/checkpoints.sqlite
```

Notes:
- The agent tool calls `GET /bookings/latest` via HTTP (API-first), so `API_BASE_URL` must point to this FastAPI server.
- If your LangGraph version supports `SqliteSaver`, checkpoints are stored in the SQLite file pointed to by `CHECKPOINT_DB`. Otherwise it falls back to in-memory checkpoints.
- Flight info for RAG-like answers is stored in the `flight_info` collection and accessible via `/flight-info/{flight_number}`.

## Frontend

Placeholder for Phase 4 (React or Streamlit).
