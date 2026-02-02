from datetime import datetime, timezone
import os
import re
import aiosqlite
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
try:
    from langgraph.checkpoint.sqlite import SqliteSaver
except ImportError:  # pragma: no cover - fallback for older langgraph
    SqliteSaver = None
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

CHECKPOINTER_KIND = "unknown"
CHECKPOINTER = None
_ASYNC_SQLITE_CONN = None
from langgraph.graph import END, StateGraph

from app.state import AgentState
from app.llm import booking_response, chat_completion, classify_intent, flight_info_response
from app.tools import (
    get_all_bookings_via_api,
    get_booking_by_flight_via_api,
    get_flight_info_via_api,
    get_latest_booking_via_api,
)
from app.users import get_user_by_id


def agent_node(state: AgentState) -> AgentState:
    messages = state.get("messages", [])
    if not messages:
        return {"messages": [AIMessage(content="Hi! Ask me about your bookings.")] }

    last_human = _last_human_message(messages)
    if last_human and _is_greeting(last_human.content):
        display_name = "there"
        if state.get("is_authenticated") and state.get("user_id"):
            user = get_user_by_id(state.get("user_id", ""))
            if user and user.username:
                display_name = user.username
        return {
            "messages": [
                AIMessage(content=f"Hi, {display_name}! How can I help you with bookings today?")
            ]
        }

    if last_human:
        intent, flight_number, info_topic = _determine_intent(last_human.content)
        if intent in {"latest", "all", "flight"}:
            return {"intent": intent, "flight_number": flight_number, "info_topic": info_topic}
        if intent == "flight_info":
            return {"intent": intent, "flight_number": flight_number, "info_topic": info_topic}

    prompt = _to_groq_messages(messages)
    try:
        content = chat_completion(prompt)
    except RuntimeError:
        content = "I can help with booking info. Try asking about your next flight."
    return {"messages": [AIMessage(content=content)], "intent": "unknown", "flight_number": "", "info_topic": ""}


async def booking_latest_node(state: AgentState) -> AgentState:
    booking = await get_latest_booking_via_api(state.get("access_token", ""))
    if not booking:
        return {
            "messages": [
                AIMessage(
                    content="I couldn't find a booking for your account. Please verify you're logged in."
                )
            ]
        }

    content = (
        "Your latest booking is "
        f"{booking.get('flight_number', '')} from {booking.get('origin', '')} "
        f"to {booking.get('destination', '')} on {_format_iso_datetime(booking.get('date', ''))} "
        f"(status: {booking.get('status', '')})."
    )
    try:
        content = booking_response(
            {
                "flight_number": booking.get("flight_number", ""),
                "origin": booking.get("origin", ""),
                "destination": booking.get("destination", ""),
                "date": _format_iso_datetime(booking.get("date", "")),
                "status": booking.get("status", ""),
            }
        )
    except RuntimeError:
        pass
    return {"messages": [AIMessage(content=content)]}


async def booking_all_node(state: AgentState) -> AgentState:
    bookings = await get_all_bookings_via_api(state.get("access_token", ""))
    if not bookings:
        return {"messages": [AIMessage(content="I couldn't find any bookings for your account.")]}
    lines = []
    for booking in bookings[:5]:
        lines.append(
            f"{booking.get('flight_number', '')}: {booking.get('origin', '')} → "
            f"{booking.get('destination', '')} on {_format_iso_datetime(booking.get('date', ''))} "
            f"({booking.get('status', '')})"
        )
    extra = ""
    if len(bookings) > 5:
        extra = f" And {len(bookings) - 5} more."
    content = "Here are your bookings: " + "; ".join(lines) + extra
    return {"messages": [AIMessage(content=content)]}


async def booking_flight_node(state: AgentState) -> AgentState:
    flight_number = state.get("flight_number", "")
    booking = await get_booking_by_flight_via_api(state.get("access_token", ""), flight_number)
    if not booking:
        return {
            "messages": [
                AIMessage(
                    content=f"I couldn't find a booking for flight {flight_number}."
                )
            ]
        }
    content = (
        f"Flight {booking.get('flight_number', '')} is from {booking.get('origin', '')} "
        f"to {booking.get('destination', '')} on {_format_iso_datetime(booking.get('date', ''))} "
        f"(status: {booking.get('status', '')})."
    )
    return {"messages": [AIMessage(content=content)]}


async def flight_info_node(state: AgentState) -> AgentState:
    flight_number = state.get("flight_number", "")
    if not flight_number:
        return {
            "messages": [
                AIMessage(content="Which flight number do you want details for?")
            ]
        }
    info = await get_flight_info_via_api(state.get("access_token", ""), flight_number)
    if not info:
        return {
            "messages": [
                AIMessage(content=f"I couldn't find info for flight {flight_number}.")
            ]
        }
    content = f"Here are the details for flight {flight_number}."
    try:
        last_human = _last_human_message(state.get("messages", []))
        question = last_human.content if last_human else "Provide flight details."
        content = flight_info_response(
            details_text=info.get("details_text", ""),
            question=question,
        )
    except RuntimeError:
        pass
    return {"messages": [AIMessage(content=content)]}


def _needs_booking_lookup(text: str) -> bool:
    lowered = text.lower()
    keywords = ("booking", "flight", "ticket", "where am i flying", "where am i travelling")
    return any(k in lowered for k in keywords)


def _is_greeting(text: str) -> bool:
    lowered = text.lower().strip()
    greetings = ("hi", "hello", "hey", "good morning", "good afternoon", "good evening")
    return any(lowered.startswith(g) for g in greetings)


def _route_from_agent(state: AgentState) -> str:
    intent = state.get("intent", "")
    if intent == "latest":
        return "booking_latest"
    if intent == "all":
        return "booking_all"
    if intent == "flight":
        return "booking_flight"
    if intent == "flight_info":
        return "flight_info"
    return END


def _last_human_message(messages: list[HumanMessage | AIMessage]):
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return message
    return None


def _format_iso_datetime(value: str) -> str:
    if not value:
        return "an unknown time"
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        local = parsed.astimezone()
        return local.strftime("%b %d, %Y at %I:%M %p %Z")
    except ValueError:
        return value


def _normalize_text(text: str) -> str:
    # Normalize unicode hyphens to ASCII for flight numbers like AI‑888.
    text = re.sub(r"[\u2010-\u2015]", "-", text)
    return " ".join(re.sub(r"[^a-z0-9\s-]", " ", text.lower()).split())


def _determine_intent(text: str) -> tuple[str, str, str]:
    normalized = _normalize_text(text)
    info_topic = ""
    if any(k in normalized for k in ("meal", "food", "snack")):
        info_topic = "meals"
    elif "wifi" in normalized:
        info_topic = "wifi"
    elif "baggage" in normalized or "luggage" in normalized:
        info_topic = "baggage"
    elif "aircraft" in normalized or "plane" in normalized or "type" in normalized:
        info_topic = "aircraft"
    elif "seat" in normalized or "legroom" in normalized or "pitch" in normalized:
        info_topic = "seating"
    flight_match = re.search(r"\b([A-Z]{2,3}-?\d{2,4})\b", text.upper().replace("–", "-").replace("—", "-").replace("‑", "-"))
    if flight_match:
        if info_topic:
            return "flight_info", flight_match.group(1), info_topic
        return "flight", flight_match.group(1), ""
    if re.search(r"\b(all|list|show)\s+(my\s+)?flight(s)?\b", normalized) or re.search(
        r"\b(all|list|show)\s+(my\s+)?booking(s)?\b", normalized
    ) or re.search(r"\b(all|list|show)\s+(my\s+)?trip(s)?\b", normalized):
        return "all", "", ""
    if re.search(r"\b(latest|next|upcoming)\b", normalized) or "where am i flying" in normalized:
        return "latest", "", ""
    if any(k in normalized for k in ("itinerary", "travel plans", "trip info")):
        return "all", "", ""
    if info_topic:
        return "flight_info", "", info_topic
    if _needs_booking_lookup(text):
        return "latest", "", ""
    try:
        data = classify_intent(text)
        return data.get("intent", "unknown"), data.get("flight_number", ""), ""
    except RuntimeError:
        return "unknown", "", ""


def _to_groq_messages(messages: list[HumanMessage | AIMessage]) -> list[dict[str, str]]:
    system_prompt = (
        "You are a secure booking assistant. Be concise and helpful. "
        "If the user asks about bookings, tell them you will check their latest booking."
    )
    converted: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for message in messages:
        if isinstance(message, HumanMessage):
            converted.append({"role": "user", "content": message.content})
        elif isinstance(message, AIMessage):
            converted.append({"role": "assistant", "content": message.content})
    return converted


def build_graph():
    global CHECKPOINTER_KIND, CHECKPOINTER
    checkpointer = None
    if SqliteSaver is not None:
        default_path = Path(__file__).resolve().parents[1] / "checkpoints.sqlite"
        checkpoint_path = Path(os.getenv("CHECKPOINT_DB", str(default_path)))
        # Use async sqlite checkpointer to support graph.ainvoke().
        # AsyncSqliteSaver.from_conn_string is a contextmanager, so keep a global connection.
        global _ASYNC_SQLITE_CONN
        _ASYNC_SQLITE_CONN = aiosqlite.connect(str(checkpoint_path))
        checkpointer = AsyncSqliteSaver(_ASYNC_SQLITE_CONN)
        CHECKPOINTER_KIND = "sqlite-async"
    else:
        checkpointer = MemorySaver()
        CHECKPOINTER_KIND = "memory"
    CHECKPOINTER = checkpointer
    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("booking_latest", booking_latest_node)
    graph.add_node("booking_all", booking_all_node)
    graph.add_node("booking_flight", booking_flight_node)
    graph.add_node("flight_info", flight_info_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges(
        "agent",
        _route_from_agent,
        {
            "booking_latest": "booking_latest",
            "booking_all": "booking_all",
            "booking_flight": "booking_flight",
            "flight_info": "flight_info",
            END: END,
        },
    )
    graph.add_edge("booking_latest", END)
    graph.add_edge("booking_all", END)
    graph.add_edge("booking_flight", END)
    graph.add_edge("flight_info", END)
    return graph.compile(checkpointer=checkpointer)


async def clear_checkpoint(thread_id: str) -> None:
    if not thread_id or CHECKPOINTER is None:
        return
    if hasattr(CHECKPOINTER, "adelete_thread"):
        await CHECKPOINTER.adelete_thread(thread_id)
    elif hasattr(CHECKPOINTER, "delete_thread"):
        CHECKPOINTER.delete_thread(thread_id)
