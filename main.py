"""
main.py — CLI entry point for the SQL Data Analyst Agent.

Concepts demonstrated:
  ✅ Full message history passed to every node (real conversational memory)
  ✅ ReAct loop: agent decides → tools execute → agent observes → repeat
  ✅ MemorySaver checkpointer (persist state across turns)
  ✅ thread_id for session tracking (each session is isolated)
  ✅ interrupt() + Command(resume=...) for human-in-the-loop
  ✅ Streaming with stream_mode="values" (see graph progress step by step)
  ✅ Error recovery loop (agent sees SQL errors and self-corrects)

Usage:
    python main.py

Example questions to try:
    - "What are the top 5 best-selling products by revenue?"
    - "Which city has the most customers?"
    - "Show me monthly revenue for the last 6 months"
    - "Which products are low on stock (less than 50 units)?"
    - "Who are our top 3 customers by total spending?"
    - "What percentage of orders were cancelled?"
"""

import logging
import uuid
import os

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────
# Set to logging.DEBUG to see every node invocation and tool call.
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s | %(name)s | %(message)s",
)

from agent.graph import graph  # import after load_dotenv so env vars are available

# ── Display helpers ────────────────────────────────────────────────────────────

DIVIDER = "─" * 60


def print_event(event: dict) -> None:
    """
    Print the latest message from a graph state event.
    Skips ToolMessages (raw tool output) to keep the UI clean —
    the agent will summarise them in plain English.
    """
    messages = event.get("messages", [])
    if not messages:
        return

    last = messages[-1]

    if isinstance(last, AIMessage):
        if last.tool_calls:
            # Agent is calling a tool — show which tool and with what args
            for tc in last.tool_calls:
                args_preview = str(tc.get("args", {}))[:120]
                print(f"\n  [Tool call] {tc['name']}({args_preview})")
        elif last.content:
            # Agent has a final answer to show
            print(f"\n{DIVIDER}")
            print(f"Agent:\n{last.content}")
            print(DIVIDER)

    elif isinstance(last, ToolMessage):
        # Show a short preview of the tool result so the user knows it ran
        preview = (last.content[:200] + "...") if len(last.content) > 200 else last.content
        print(f"\n  [Tool result preview]\n{preview}")


def stream_until_interrupt(input_payload, config: dict) -> bool:
    """
    Stream the graph until it either finishes or hits an interrupt().
    Returns True if the graph was interrupted (human review pending).
    """
    for event in graph.stream(input_payload, config, stream_mode="values"):
        print_event(event)

    # Check if the graph is paused at an interrupt
    state = graph.get_state(config)
    return bool(state.next)  # True = interrupted, False = finished


def handle_human_review(config: dict) -> bool:
    """
    Surface the interrupt data to the user, collect their decision,
    and resume the graph with Command(resume=...).

    Returns True if the graph finished after resuming, False if it
    was interrupted again (another revision round).
    """
    state      = graph.get_state(config)
    interrupts = state.tasks[0].interrupts if state.tasks else []

    if not interrupts:
        return True

    interrupt_data = interrupts[0].value
    proposed       = interrupt_data.get("proposed_answer", "")

    print(f"\n{'='*60}")
    print("HUMAN REVIEW REQUIRED")
    print(f"{'='*60}")
    print(f"Proposed answer:\n\n{proposed}\n")

    while True:
        decision = input("Approve this answer? (y/n): ").strip().lower()
        if decision in ("y", "n"):
            break
        print("Please enter 'y' or 'n'.")

    if decision == "y":
        resume_value = {"approved": True}
    else:
        feedback = input("What should the agent change? ").strip()
        resume_value = {"approved": False, "feedback": feedback or "Please improve the answer."}

    # Resume the graph with the human's decision
    interrupted = stream_until_interrupt(Command(resume=resume_value), config)
    if interrupted:
        return handle_human_review(config)  # another revision round
    return True


# ── Main chat loop ─────────────────────────────────────────────────────────────

def run():
    # Generate a unique session ID — each session gets its own isolated state.
    # The checkpointer stores state keyed by thread_id, so different sessions
    # never interfere with each other.
    thread_id = str(uuid.uuid4())
    config    = {"configurable": {"thread_id": thread_id}}

    print(f"\n{DIVIDER}")
    print("  SQL Data Analyst Agent  |  Powered by LangGraph")
    print(f"{DIVIDER}")
    print("Ask me anything about the e-commerce database.")
    print("Type 'exit' to quit.\n")
    print(f"Session ID: {thread_id[:8]}...\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "q"):
            print("Goodbye!")
            break

        # ── Initial graph invocation ─────────────────────────────────────────
        # We pass the new user message. LangGraph's add_messages reducer
        # automatically appends it to the existing message history in state,
        # so the agent always has full conversational context.
        initial_state = {
            "messages":      [{"role": "user", "content": user_input}],
            "retry_count":   0,
            "query_approved": False,
        }

        print(f"\n  [Thinking...]\n")

        try:
            interrupted = stream_until_interrupt(initial_state, config)

            if interrupted:
                handle_human_review(config)

        except Exception as e:
            print(f"\nError: {e}")
            logging.exception("Unhandled error during graph execution")

        print()


if __name__ == "__main__":
    run()
