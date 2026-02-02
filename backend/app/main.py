from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, field_validator
from dotenv import load_dotenv
from pathlib import Path

from app.auth import (
    AuthResult,
    create_refresh_token,
    create_token,
    decode_bearer_token,
    decode_refresh_token,
)
import app.graph as graph_module
from app.users import ensure_demo_user, get_user_by_username, verify_password

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

app = FastAPI(title="GateReady")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

graph = graph_module.build_graph()
_REVOKED_REFRESH_TOKENS: set[str] = set()


class ChatRequest(BaseModel):
    message: str


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class SeedResponse(BaseModel):
    status: str


class BookingCreateRequest(BaseModel):
    user_id: str
    flight_number: str
    origin: str
    destination: str
    date: str
    status: str

    @field_validator("date")
    @classmethod
    def validate_date(cls, value: str) -> str:
        from datetime import datetime

        try:
            # Expecting ISO 8601 string like 2026-04-01T09:30:00Z
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("date must be ISO 8601 (e.g. 2026-04-01T09:30:00Z)") from exc
        return value


class BookingCreateResponse(BaseModel):
    booking_id: str


class BookingResponse(BaseModel):
    booking_id: str
    user_id: str
    flight_number: str
    origin: str
    destination: str
    date: str
    status: str


class FlightInfoResponse(BaseModel):
    flight_number: str
    details_text: str


@app.get("/health")
async def health():
    return {"status": "ok", "checkpointer": graph_module.CHECKPOINTER_KIND}


@app.on_event("startup")
async def startup():
    # Seed a demo user in MongoDB for local testing.
    ensure_demo_user()


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    auth_header = request.headers.get("Authorization")
    auth: AuthResult = decode_bearer_token(auth_header)
    request.state.user_id = auth.user_id
    request.state.is_authenticated = auth.is_authenticated
    access_token = None
    if auth_header:
        parts = auth_header.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            access_token = parts[1]
    request.state.access_token = access_token
    return await call_next(request)


@app.post("/login")
async def login(req: LoginRequest):
    user = get_user_by_username(req.username)
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    access_token = create_token(user.user_id)
    refresh_token = create_refresh_token(user.user_id)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@app.post("/refresh")
async def refresh(req: RefreshRequest):
    auth = decode_refresh_token(req.refresh_token)
    if not auth.is_authenticated or not auth.user_id or not auth.token_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    if auth.token_id in _REVOKED_REFRESH_TOKENS:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked")
    _REVOKED_REFRESH_TOKENS.add(auth.token_id)
    access_token = create_token(auth.user_id)
    refresh_token = create_refresh_token(auth.user_id)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@app.post("/logout")
async def logout(req: LogoutRequest):
    auth = decode_refresh_token(req.refresh_token)
    if not auth.is_authenticated or not auth.token_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    _REVOKED_REFRESH_TOKENS.add(auth.token_id)
    if auth.user_id:
        await graph_module.clear_checkpoint(auth.user_id)
    return {"status": "ok"}


@app.post("/seed", response_model=SeedResponse)
async def seed():
    # Creates demo user + booking to initialize MongoDB collections.
    ensure_demo_user()
    from app.db import get_bookings_collection
    from app.db import get_flight_info_collection

    bookings = get_bookings_collection()
    existing = bookings.find_one({"_id": "booking_101"})
    if not existing:
        bookings.insert_one(
            {
                "_id": "booking_101",
                "user_id": "user_123",
                "flight_number": "AI-888",
                "origin": "Pune",
                "destination": "Delhi",
                "date": "2026-03-10T14:00:00Z",
                "status": "Confirmed",
            }
        )
    flight_info = get_flight_info_collection()
    if not flight_info.find_one({"flight_number": "AI-888"}):
        flight_info.insert_one(
            {
                "flight_number": "AI-888",
                "details_text": (
                    "Flight AI-888 uses an Airbus A320. Complimentary snack and beverage are provided. "
                    "Baggage allowance is 15kg checked and 7kg cabin. Wi-Fi is not available. "
                    "Seat pitch is 30 in. USB charging is available on select rows."
                ),
            }
        )
    if not flight_info.find_one({"flight_number": "AI-999"}):
        flight_info.insert_one(
            {
                "flight_number": "AI-999",
                "details_text": (
                    "Flight AI-999 uses a Boeing 737-8. Complimentary meal for flights over 2 hours. "
                    "Baggage allowance is 20kg checked and 7kg cabin. Wi-Fi is available (paid). "
                    "Seat pitch is 31 in. Exit rows offer extra legroom."
                ),
            }
        )
    return {"status": "seeded"}


@app.post("/bookings", response_model=BookingCreateResponse)
async def create_booking(req: BookingCreateRequest, request: Request):
    if not request.state.is_authenticated:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    if req.user_id != request.state.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot create booking for another user")
    from app.db import get_bookings_collection

    booking = {
        "user_id": req.user_id,
        "flight_number": req.flight_number,
        "origin": req.origin,
        "destination": req.destination,
        "date": req.date,
        "status": req.status,
    }
    result = get_bookings_collection().insert_one(booking)
    return {"booking_id": str(result.inserted_id)}


@app.get("/bookings", response_model=list[BookingResponse])
async def list_bookings(
    request: Request,
    origin: str | None = None,
    destination: str | None = None,
    status: str | None = None,
):
    if not request.state.is_authenticated:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    user_id = request.state.user_id
    from app.db import get_bookings_collection

    query: dict[str, str] = {"user_id": user_id}
    if origin:
        query["origin"] = origin
    if destination:
        query["destination"] = destination
    if status:
        query["status"] = status
    cursor = get_bookings_collection().find(query).sort("date", -1)
    results: list[BookingResponse] = []
    for doc in cursor:
        results.append(
            BookingResponse(
                booking_id=str(doc.get("_id")),
                user_id=str(doc.get("user_id", "")),
                flight_number=str(doc.get("flight_number", "")),
                origin=str(doc.get("origin", "")),
                destination=str(doc.get("destination", "")),
                date=str(doc.get("date", "")),
                status=str(doc.get("status", "")),
            )
        )
    return results


@app.get("/bookings/latest", response_model=BookingResponse)
async def latest_booking(request: Request):
    if not request.state.is_authenticated:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    from app.tools import get_latest_booking_db

    booking = get_latest_booking_db(request.state.user_id or "")
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No booking found")
    return BookingResponse(
        booking_id=str(booking.get("_id")),
        user_id=str(booking.get("user_id", "")),
        flight_number=str(booking.get("flight_number", "")),
        origin=str(booking.get("origin", "")),
        destination=str(booking.get("destination", "")),
        date=str(booking.get("date", "")),
        status=str(booking.get("status", "")),
    )


@app.get("/bookings/flight/{flight_number}", response_model=BookingResponse)
async def booking_by_flight(flight_number: str, request: Request):
    if not request.state.is_authenticated:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    from app.db import get_bookings_collection

    booking = get_bookings_collection().find_one(
        {"user_id": request.state.user_id, "flight_number": flight_number}
    )
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No booking found")
    return BookingResponse(
        booking_id=str(booking.get("_id")),
        user_id=str(booking.get("user_id", "")),
        flight_number=str(booking.get("flight_number", "")),
        origin=str(booking.get("origin", "")),
        destination=str(booking.get("destination", "")),
        date=str(booking.get("date", "")),
        status=str(booking.get("status", "")),
    )


@app.get("/flight-info/{flight_number}", response_model=FlightInfoResponse)
async def flight_info(flight_number: str, request: Request):
    if not request.state.is_authenticated:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    from app.db import get_flight_info_collection

    info = get_flight_info_collection().find_one({"flight_number": flight_number})
    if not info:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No flight info found")
    return FlightInfoResponse(
        flight_number=str(info.get("flight_number", "")),
        details_text=str(info.get("details_text", "")),
    )


@app.post("/chat")
async def chat(req: ChatRequest, request: Request):
    # Phase 3: user_id is injected by middleware from the JWT
    state = {
        "messages": [HumanMessage(content=req.message)],
        "user_id": request.state.user_id or "",
        "is_authenticated": bool(request.state.is_authenticated),
        "access_token": request.state.access_token or "",
        "intent": "unknown",
        "flight_number": "",
        "info_topic": "",
    }
    thread_id = request.state.user_id or "anon"
    result = await graph.ainvoke(
        state,
        config={"configurable": {"thread_id": thread_id}},
    )
    # result["messages"] is a list of AnyMessage; return last assistant message
    messages = result.get("messages", [])
    content = messages[-1].content if messages else ""
    return {"reply": content}
