"""
Node functions — the steps in the agent graph.

Every node receives the current State, does some work, and returns a dict
that gets MERGED into the State. Nodes never replace the state entirely,
they only update the keys they return.
"""

import os
import logging

from langchain.chat_models import init_chat_model
from langgraph.prebuilt import ToolNode
from langgraph.types import interrupt

from agent.state import AgentState
from agent.tools import tools

logger = logging.getLogger(__name__)

MAX_REVISIONS = 3  # Maximum times a human can request a revision per session

# ── LLM Setup ────────────────────────────────────────────────────────────────
# init_chat_model reads the model name from the environment variable MODEL.
# bind_tools() tells the LLM which tools it can call and sends their schemas.
# After this, the LLM can decide on its own when and how to call each tool.

_llm = init_chat_model(os.getenv("MODEL", "gpt-4o"), temperature=0)
llm_with_tools = _llm.bind_tools(tools)

# ToolNode from langgraph.prebuilt handles the tool execution loop for us.
# When the LLM returns a message with tool_calls, ToolNode:
#   1. Parses each tool call (name + arguments)
#   2. Calls the actual Python function
#   3. Returns the result as a ToolMessage back into state["messages"]
tool_executor = ToolNode(tools)

# ── System Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = f"""You are an expert SQL data analyst assistant. You help users \
query an e-commerce SQLite database to uncover business insights.

Your step-by-step workflow:
1. Call get_database_schema to understand the available tables and columns.
2. Write a precise, efficient SQL query to answer the user's question.
3. Call execute_sql_query to run the query.
4. If you get a SQL error, analyse the error message, correct the query, and retry.
   You may retry up to {MAX_REVISIONS} times before giving up.
5. After getting results, explain them in plain English with business context.
   Highlight trends, top items, or anomalies where relevant.

Rules:
- ALWAYS inspect the schema first — never guess table or column names.
- Only use SELECT statements.
- Always add a LIMIT clause to avoid huge result sets.
- If a query returns no results, suggest why and offer an alternative query.
"""


# ── Node 1: SQL Agent ─────────────────────────────────────────────────────────

def sql_agent(state: AgentState) -> dict:
    """
    Core reasoning node.

    The LLM receives the full conversation history (all messages) plus the
    system prompt. It decides to either:
      (a) Call a tool  → returns an AIMessage with tool_calls populated
      (b) Give a final answer → returns an AIMessage with plain text content

    Returning full state["messages"] (not just the last message) gives the LLM
    complete context — it remembers prior tool results and can self-correct.
    """
    logger.info(
        "[agent] Invoking LLM | messages=%d | retries=%d",
        len(state["messages"]),
        state.get("retry_count", 0),
    )

    # Build full message list: system prompt + entire conversation history
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + list(state["messages"])
    response = llm_with_tools.invoke(messages)

    return {"messages": [response]}


# ── Node 2: Human Review ──────────────────────────────────────────────────────

def human_review_node(state: AgentState) -> dict:
    """
    Human-in-the-loop node.

    interrupt() PAUSES the graph here and surfaces data to the caller
    (main.py). The graph stays frozen until the caller resumes it with:

        graph.stream(Command(resume={"approved": True}), config)
        graph.stream(Command(resume={"approved": False, "feedback": "..."}), config)

    This pattern is critical for production agents that take consequential
    actions (sending emails, writing to DBs, etc.) — always get human sign-off.
    """
    last_message = state["messages"][-1]
    logger.info("[human_review] Interrupting for approval.")

    # Pause the graph — main.py receives this dict via get_state()
    human_decision = interrupt({
        "proposed_answer": last_message.content,
        "instructions": "Type 'y' to approve or 'n' to request a revision.",
    })

    if human_decision.get("approved", False):
        logger.info("[human_review] Approved.")
        return {"query_approved": True}

    # Human wants changes — inject feedback as a new user message so the
    # agent sees it on the next turn and can revise its answer.
    feedback = human_decision.get("feedback", "Please revise your answer.")
    logger.info("[human_review] Revision requested: %s", feedback)
    return {
        "messages": [{"role": "user", "content": f"[Revision requested]: {feedback}"}],
        "query_approved": False,
        "retry_count": state.get("retry_count", 0) + 1,
    }


# ── Edge Functions (routing logic) ────────────────────────────────────────────
# Edge functions are NOT nodes — they don't modify state.
# They just read the current state and return a string that maps to the next node.

def should_continue(state: AgentState) -> str:
    """
    Called after the sql_agent node.
    Decides what happens next based on the LLM's last response.

    Returns:
        "tools"        → LLM made tool calls, execute them
        "human_review" → LLM gave a final answer, get human approval
        "end"          → Revision limit exceeded, stop gracefully
    """
    last_message = state["messages"][-1]

    # If the LLM returned tool calls, route to the tool executor
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        logger.info("[edge] Routing to tools.")
        return "tools"

    # Safety valve: if human has requested too many revisions, stop
    if state.get("retry_count", 0) >= MAX_REVISIONS:
        logger.warning("[edge] Max revisions reached. Ending.")
        return "end"

    logger.info("[edge] Routing to human_review.")
    return "human_review"


def after_human_review(state: AgentState) -> str:
    """
    Called after the human_review node.
    Decides what happens next based on the human's decision.

    Returns:
        "end"   → Human approved, we're done
        "agent" → Human wants revision, loop back to the agent
    """
    if state.get("query_approved", False):
        return "end"
    return "agent"
