"""
SQL Tools — what the agent can DO.

Each function decorated with @tool becomes a tool the LLM can call.
The docstring is what the LLM reads to decide WHEN to use a tool,
so they must be clear and descriptive.
"""

import os
import sqlite3
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _get_db_path() -> str:
    return os.getenv("DB_PATH", "ecommerce.db")


def _get_connection() -> sqlite3.Connection:
    """Return a SQLite connection with row factory for readable output."""
    conn = sqlite3.connect(_get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


# ── Tool 1: Schema Inspector ─────────────────────────────────────────────────

@tool
def get_database_schema() -> str:
    """
    Retrieve the complete database schema — all tables, their columns,
    data types, and row counts. ALWAYS call this tool first before writing
    any SQL query so you understand what data is available.
    """
    try:
        conn = _get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]

        if not tables:
            conn.close()
            return "No tables found in the database."

        schema_parts = []
        for table in tables:
            cursor.execute(f"PRAGMA table_info({table})")
            columns = cursor.fetchall()
            col_defs = ", ".join(
                f"{col['name']} ({col['type']})" for col in columns
            )

            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            row_count = cursor.fetchone()[0]

            schema_parts.append(
                f"Table: {table}  [{row_count:,} rows]\n  Columns: {col_defs}"
            )

        conn.close()
        return "\n\n".join(schema_parts)

    except sqlite3.Error as e:
        logger.error("Schema fetch error: %s", e)
        return f"Error retrieving schema: {e}"


# ── Tool 2: SQL Executor ──────────────────────────────────────────────────────

@tool
def execute_sql_query(query: str) -> str:
    """
    Execute a SELECT SQL query against the e-commerce database and return
    the results as a formatted table. Only SELECT statements are allowed.
    Results are capped at 100 rows — use LIMIT/OFFSET for pagination.
    If this returns an error, fix the SQL and try again.
    """
    # ── Safety checks ────────────────────────────────────────────────────────
    cleaned = query.strip()
    if not cleaned.upper().startswith("SELECT"):
        return "Error: Only SELECT statements are permitted."

    blocked_keywords = ["DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE", "TRUNCATE"]
    upper_query = cleaned.upper()
    for kw in blocked_keywords:
        if kw in upper_query:
            return f"Error: '{kw}' statements are not allowed for safety."

    # ── Execute ──────────────────────────────────────────────────────────────
    try:
        conn = sqlite3.connect(_get_db_path())
        cursor = conn.cursor()

        logger.info("Executing SQL: %s", cleaned)
        cursor.execute(cleaned)

        rows = cursor.fetchmany(100)
        columns = [desc[0] for desc in cursor.description]
        conn.close()

        if not rows:
            return "Query executed successfully but returned no results."

        # ── Format as aligned table ──────────────────────────────────────────
        col_widths = [
            max(len(col), max(len(str(row[i])) for row in rows))
            for i, col in enumerate(columns)
        ]

        header  = " | ".join(col.ljust(w) for col, w in zip(columns, col_widths))
        divider = "-+-".join("-" * w for w in col_widths)
        data    = [
            " | ".join(str(v).ljust(w) for v, w in zip(row, col_widths))
            for row in rows
        ]

        result_lines = [header, divider] + data
        if len(rows) == 100:
            result_lines.append("(Capped at 100 rows. Use LIMIT/OFFSET for more.)")

        return f"Rows returned: {len(rows)}\n\n" + "\n".join(result_lines)

    except sqlite3.Error as e:
        logger.warning("SQL execution error: %s", e)
        return f"SQL Error: {e}\n\nHint: Check column names and table names using get_database_schema."


# ── Exported list used by nodes.py and graph.py ──────────────────────────────
tools = [get_database_schema, execute_sql_query]
