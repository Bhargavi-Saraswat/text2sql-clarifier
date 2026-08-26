"""
Text-to-SQL with a Clarification Engine — Streamlit demo.

Run:
    $env:GROQ_API_KEY="gsk_..."   (PowerShell)  /  export GROQ_API_KEY=gsk_...  (bash)
    streamlit run app.py
"""

import os
import subprocess
import sys

import streamlit as st

from core.schema import get_schema_description
from core.clarifier import resolve, ClarificationTurn
from core.executor import run_query, UnsafeQueryError

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "sample.db")

st.set_page_config(page_title="Text-to-SQL Clarifier", layout="wide")
st.title("🗄️ Text-to-SQL with a Clarification Engine")
st.caption(
    "Ask a question about the sample e-commerce database in plain English. "
    "If your question is genuinely ambiguous, the system will ask you a "
    "clarifying question instead of guessing."
)

# --- session state: one dict of transcript entries per turn, so the
#     rendering loop below just switches on entry["kind"] instead of
#     unpacking positional tuples. ---
st.session_state.setdefault("schema_text", get_schema_description(DB_PATH))
st.session_state.setdefault("pending_question", None)   # NL question currently being resolved
st.session_state.setdefault("history", [])               # list[ClarificationTurn] for that question
st.session_state.setdefault("clarifier_prompt", None)     # clarifying question awaiting the user's answer
st.session_state.setdefault("log", [])                    # transcript shown in the chat

with st.sidebar:
    st.subheader("Schema")
    st.code(st.session_state.schema_text, language="text")
    if st.button("Regenerate sample data"):
        subprocess.run([sys.executable, os.path.join("data", "generate_db.py")], check=True)
        st.session_state.schema_text = get_schema_description(DB_PATH)
        st.rerun()


def run_pipeline(nl_question: str) -> None:
    """Runs one clarify-or-generate turn and appends the outcome to the log."""
    result = resolve(st.session_state.schema_text, nl_question, st.session_state.history)

    if result.action == "clarify":
        st.session_state.pending_question = nl_question
        st.session_state.clarifier_prompt = result.question
        st.session_state.log.append({"kind": "clarify", "question": result.question, "reasoning": result.reasoning})
        return

    st.session_state.log.append({"kind": "sql", "sql": result.sql, "assumptions": result.assumptions})
    try:
        df = run_query(DB_PATH, result.sql)
        st.session_state.log.append({"kind": "result", "df": df})
    except UnsafeQueryError as e:
        st.session_state.log.append({"kind": "error", "message": str(e)})

    st.session_state.pending_question = None
    st.session_state.history = []
    st.session_state.clarifier_prompt = None


# --- render transcript ---
for entry in st.session_state.log:
    with st.chat_message("assistant"):
        if entry["kind"] == "clarify":
            st.markdown(f"**Clarifying question:** {entry['question']}")
            if entry["reasoning"]:
                st.caption(f"Why: {entry['reasoning']}")
        elif entry["kind"] == "sql":
            st.code(entry["sql"], language="sql")
            if entry["assumptions"]:
                st.caption("Assumptions made: " + "; ".join(entry["assumptions"]))
        elif entry["kind"] == "result":
            df = entry["df"]
            if df.empty:
                st.write("Query ran successfully (no rows returned).")
            else:
                st.dataframe(df, use_container_width=True)
                if len(df) >= 500:
                    st.caption("Results truncated at 500 rows.")
        elif entry["kind"] == "error":
            st.error(entry["message"])

# --- input: either answering a pending clarification, or asking a new question ---
if st.session_state.clarifier_prompt:
    st.info(f"Clarification needed: {st.session_state.clarifier_prompt}")
    if answer := st.chat_input("Your answer..."):
        with st.chat_message("user"):
            st.write(answer)
        st.session_state.history.append(
            ClarificationTurn(question=st.session_state.clarifier_prompt, answer=answer)
        )
        st.session_state.clarifier_prompt = None
        run_pipeline(st.session_state.pending_question)
        st.rerun()
else:
    if question := st.chat_input("Ask a question about the database..."):
        with st.chat_message("user"):
            st.write(question)
        run_pipeline(question)
        st.rerun()

with st.expander("💡 Try these"):
    st.markdown(
        "- `Show me total revenue by region` — unambiguous, runs straight away\n"
        "- `Who are the top customers?` — ambiguous: by revenue, order count, or recency?\n"
        "- `List recent orders` — ambiguous: order date or delivered date, and what counts as recent?\n"
        "- `Show active orders` — ambiguous: does 'active' include pending, shipped, or both?\n"
        "- `Top products in Electronics` — ambiguous: ranked by revenue or units sold?"
    )
