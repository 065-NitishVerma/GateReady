from typing import TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import Annotated


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    user_id: str
    is_authenticated: bool
    access_token: str
    intent: str
    flight_number: str
    info_topic: str
