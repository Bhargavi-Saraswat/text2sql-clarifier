"""
Executes generated SQL safely.

Two layers of protection:
  1. sqlglot parses the SQL and checks it's a single SELECT statement —
     this is real parsing, not a regex guess, so it isn't fooled by
     keywords hiding in strings/comments the way a regex blocklist can be.
  2. The SQLite connection itself is opened read-only (mode=ro URI), so
     even a write statement that somehow got past step 1 would fail at
     the database level.
"""

import sqlite3
import pandas as pd
import sqlglot
from sqlglot.expressions import Select

ROW_LIMIT = 500


class UnsafeQueryError(Exception):
    pass


def validate_select_only(sql: str) -> None:
    try:
        statements = sqlglot.parse(sql, dialect="sqlite")
    except sqlglot.errors.ParseError as e:
        raise UnsafeQueryError(f"Not valid SQL: {e}")

    if len(statements) != 1:
        raise UnsafeQueryError("Only a single statement is allowed.")
    if not isinstance(statements[0], Select):
        raise UnsafeQueryError("Only SELECT statements are allowed.")


def run_query(db_path: str, sql: str) -> pd.DataFrame:
    """Runs a validated SELECT and returns results as a DataFrame,
    capped at ROW_LIMIT rows."""
    validate_select_only(sql)

    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        return pd.read_sql_query(sql, conn).head(ROW_LIMIT)
    finally:
        conn.close()
