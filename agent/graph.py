"""
Graph construction — wires all nodes and edges together.

The graph defines the FLOW of the agent:

    START
      │
    [agent]  ←──────────────────────────┐
      │                                  │
      ├─ has tool_calls? → [tools] ──────┘  (ReAct loop: think → act → think)
      │
      └─ final answer?  → [human_review]
                              │
                              ├─ approved  → END
                              │
                              └─ revision  → [agent]  (revision loop)

Key production features used here:
  - MemorySaver checkpointer → persists state across turns (survives restarts)
  - interrupt() in human_review_node → human-in-the-loop pause/resume
  - Conditional edges → dynamic routing based on state
"""

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from agent.state import AgentState
from agent.nodes import (
    sql_agent,
    human_review_node,
    tool_executor,
    should_continue,
    after_human_review,
)


def build_graph():
    """Build and compile the SQL Agent graph."""
    builder = StateGraph(AgentState)

    # ── Register nodes ────────────────────────────────────────────────────────
    builder.add_node("agent", sql_agent)
    builder.add_node("tools", tool_executor)       # from langgraph.prebuilt
    builder.add_node("human_review", human_review_node)

    # ── Define edges (the flow) ───────────────────────────────────────────────
    builder.add_edge(START, "agent")

    # After agent runs: route to tools OR human_review OR end (via should_continue)
    builder.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "human_review": "human_review",
            "end": END,
        },
    )

    # After tool execution: ALWAYS go back to agent (this creates the ReAct loop)
    # Agent sees tool results in messages and decides what to do next
    builder.add_edge("tools", "agent")

    # After human review: route to end (approved) or agent (revision requested)
    builder.add_conditional_edges(
        "human_review",
        after_human_review,
        {
            "end": END,
            "agent": "agent",
        },
    )

    # ── Checkpointer (persistence) ────────────────────────────────────────────
    # MemorySaver stores state in RAM — good for development.
    # For production, swap this with SqliteSaver or PostgresSaver:
    #
    #   from langgraph.checkpoint.sqlite import SqliteSaver
    #   checkpointer = SqliteSaver.from_conn_string("checkpoints.db")
    #
    # The checkpointer is keyed by thread_id (passed in config).
    # Each unique thread_id is an independent conversation session.
    checkpointer = MemorySaver()

    return builder.compile(checkpointer=checkpointer)


# Module-level singleton — imported by main.py
graph = build_graph()
