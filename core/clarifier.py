"""
The clarification engine.

This is the heart of the project: instead of always forcing a
natural-language question into SQL (and silently guessing when it's
ambiguous), we ask the model to first judge whether it CAN be answered
unambiguously against the given schema. If not, it produces a targeted
clarifying question instead of a query.

Design:
  - Single structured call per turn, returns one of:
      {"action": "clarify", "question": "...", "reasoning": "..."}
      {"action": "generate", "sql": "...", "reasoning": "...", "assumptions": [...]}
  - Ambiguity we specifically want it to catch (matches the schema's
    quirks in data/generate_db.py):
      * vague time ranges ("recent", "last few") when there are two
        date columns (order_date vs delivered_date)
      * vague ranking ("top customers") without a metric (revenue?
        order count? most recent?)
      * ambiguous status filters ("active orders" — pending? shipped?
        both?)
      * ambiguous entity references ("top products" — by category or
        overall? by revenue or units sold?)
  - Conversation history of prior clarification Q&A is passed back in
    on each turn so the model has the accumulated context.
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field
from .llm_client import call_json

SYSTEM_PROMPT = """You are a careful Text-to-SQL assistant for a SQLite e-commerce database.

You will be given:
1. The database schema (tables, columns, foreign keys, and value hints for enum-like columns)
2. The user's natural language question
3. Any prior clarification exchanges for this same question

Your job each turn is to decide ONE of two things:

A) The question is answerable UNAMBIGUOUSLY against this schema as written.
   -> Return {"action": "generate", "sql": "<SELECT statement>", "reasoning": "<short reasoning>", "assumptions": ["<any minor assumption you made>", ...]}

B) The question is genuinely ambiguous in a way that would change the SQL
   or the meaning of the result — not just "could theoretically be phrased
   more precisely."
   -> Return {"action": "clarify", "question": "<one specific, concrete clarifying question, ideally with concrete options>", "reasoning": "<why this is ambiguous>"}

Rules:
- Only ask a clarifying question when the ambiguity would actually change the query or its meaning (e.g. which date column to use, what "top" is ranked by, which status values count as "active"). Do not ask about things with an obvious, safe default.
- Ask at most ONE clarifying question per turn. If there were prior clarifications in this conversation, incorporate their answers and only ask again if something NEW is still ambiguous.
- Never invent columns or tables that are not in the schema.
- Only ever produce SELECT statements. Never write/modify statements.
- SQL must be valid SQLite syntax.
- When you do generate SQL, note any minor default assumptions you made (e.g. "assumed 'top' means by total revenue") in "assumptions" so the user can see them.
- Respond with ONLY the JSON object. No prose, no markdown fences.
"""


class ClarificationTurn(BaseModel):
    question: str
    answer: str


class ClarifierResult(BaseModel):
    """Validated shape of the model's JSON response — pydantic raises a
    clear error if the model ever returns something malformed, instead
    of an AttributeError three lines later somewhere else."""
    action: Literal["clarify", "generate"]
    question: Optional[str] = None
    sql: Optional[str] = None
    reasoning: Optional[str] = None
    assumptions: list[str] = Field(default_factory=list)


def build_user_prompt(schema_text: str, nl_question: str, history: list[ClarificationTurn]) -> str:
    parts = [f"SCHEMA:\n{schema_text}", f"\nUSER QUESTION:\n{nl_question}"]
    if history:
        parts.append("\nPRIOR CLARIFICATIONS FOR THIS QUESTION:")
        for turn in history:
            parts.append(f"  Q: {turn.question}\n  A: {turn.answer}")
    return "\n".join(parts)


def resolve(schema_text: str, nl_question: str, history: list[ClarificationTurn] = None) -> ClarifierResult:
    history = history or []
    user_prompt = build_user_prompt(schema_text, nl_question, history)
    raw = call_json(SYSTEM_PROMPT, user_prompt)
    return ClarifierResult.model_validate(raw)
