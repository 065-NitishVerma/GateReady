from __future__ import annotations

import os
from functools import lru_cache

from groq import Groq
import json


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@lru_cache(maxsize=1)
def _client() -> Groq:
    return Groq(api_key=_require_env("GROQ_API_KEY"))


def _model_name() -> str:
    return os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")


def chat_completion(messages: list[dict[str, str]]) -> str:
    response = _client().chat.completions.create(
        model=_model_name(),
        messages=messages,
        temperature=0.3,
    )
    return response.choices[0].message.content or ""


def booking_response(booking: dict[str, str]) -> str:
    system_prompt = (
        "You are a secure booking assistant. Use ONLY the booking data provided. "
        "Respond in one short sentence. Do not invent details."
    )
    user_prompt = (
        "Booking data:\n"
        f"Flight: {booking.get('flight_number', '')}\n"
        f"From: {booking.get('origin', '')}\n"
        f"To: {booking.get('destination', '')}\n"
        f"Date: {booking.get('date', '')}\n"
        f"Status: {booking.get('status', '')}\n"
        "Reply to the user."
    )
    return chat_completion(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    )


def classify_intent(message: str) -> dict[str, str]:
    system_prompt = (
        "Classify user intent for a booking assistant. "
        "Return JSON with keys: intent (one of latest, all, flight, flight_info, unknown) and flight_number. "
        "Only include a flight_number if explicitly mentioned (e.g., AI-123)."
    )
    raw = chat_completion(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ]
    )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"intent": "unknown", "flight_number": ""}
    intent = data.get("intent", "unknown")
    flight_number = data.get("flight_number", "") or ""
    if intent not in {"latest", "all", "flight", "flight_info", "unknown"}:
        intent = "unknown"
    if not isinstance(flight_number, str):
        flight_number = ""
    return {"intent": intent, "flight_number": flight_number}


def flight_info_response(details_text: str, question: str) -> str:
    system_prompt = (
        "You are a secure booking assistant. Use ONLY the flight info provided. "
        "Answer the user's question in one or two short sentences. Do not invent details."
    )
    user_prompt = (
        "Flight info document:\n"
        f"{details_text}\n\n"
        f"User question: {question}\n"
        "Answer based only on the document."
    )
    return chat_completion(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    )
