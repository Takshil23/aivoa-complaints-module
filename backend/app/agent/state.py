"""LangGraph agent state."""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    session_id: str

    # Conversation transcript (LangGraph appends via the add_messages reducer).
    messages: Annotated[list[AnyMessage], add_messages]

    # --- inputs for this turn ---
    user_input: str
    document_text: str
    filename: str

    # --- the record being built ---
    form_sections: list[dict[str, Any]]
    risk: dict[str, str]
    status: str

    # --- outputs of this turn ---
    route: str
    tool_used: str
    reply: str
    patch: dict[str, str]
