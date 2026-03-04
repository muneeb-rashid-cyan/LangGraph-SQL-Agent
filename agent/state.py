"""
State definition for the SQL Agent.

State is the shared memory of the entire graph — every node reads from it
and writes to it. Think of it like a whiteboard passed between all steps.
"""

from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    # Full conversation history.
    # `add_messages` is a reducer: new messages are APPENDED, not replaced.
    # This gives the LLM full context of every prior turn.
    messages: Annotated[list, add_messages]

    # How many times a human has requested a revision in this session.
    # Used as a safety valve to prevent infinite revision loops.
    retry_count: int

    # Set to True by the human_review node when the human approves the answer.
    # Read by the after_human_review edge function to decide what to do next.
    query_approved: bool
