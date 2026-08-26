# Text-to-SQL with a Clarification Engine

Turns natural language questions into SQL against a sample e-commerce
database — but instead of silently guessing on ambiguous questions,
it asks a targeted clarifying question first.

**Example:** "Show me the top customers" is ambiguous — top by revenue?
by order count? most recent signups? The system detects this and asks
you before generating SQL, instead of quietly picking one interpretation.

## Why this exists

Most Text-to-SQL demos generate a query no matter what you ask, even
when the question is underspecified — which produces SQL that's
*syntactically* correct but answers a question you didn't actually ask.
This project adds a decision step before generation: given the schema
and the question, is this answerable unambiguously? If not, ask.

## Architecture

```
User question
     |
     v
[schema.py] --- schema + value hints (enum columns like status, region)
     |
     v
[clarifier.py] -- LLM call, structured JSON output:
     |               {"action": "clarify", "question": "..."}
     |            or {"action": "generate", "sql": "...", "assumptions": [...]}
     |
     +-- if clarify: ask user, append Q&A to history, re-run clarifier.py
     |
     v
[executor.py] --- validates SELECT-only, runs against read-only SQLite,
                   row-limited results
     |
     v
[app.py] --- Streamlit chat UI showing the transcript
```

## Setup

```bash
pip install -r requirements.txt
python data/generate_db.py       # regenerate the sample DB if needed (already included)

# Free Groq API key: https://console.groq.com/keys
export GROQ_API_KEY=gsk_...      # bash/macOS/Linux
# $env:GROQ_API_KEY="gsk_..."    # PowerShell equivalent

streamlit run app.py
```

## Key design decisions (useful for interview talking points)

- **Ambiguity detection is a single structured LLM call**, not a
  separate classifier — the schema + value hints (distinct values for
  low-cardinality columns like `status`, `region`, `category`) give the
  model enough signal to tell "resolvable with a sane default" apart
  from "actually changes the query."
- **Conversation memory for clarification**: prior Q&A pairs for the
  current question are passed back into every follow-up call, so a
  multi-turn clarification converges instead of looping.
- **Safety is layered, not just prompted**: the system prompt restricts
  to SELECT, `executor.py` re-validates by actually parsing the SQL
  with `sqlglot` (a real parser, not a regex keyword guess — so it
  isn't fooled by SQL-looking text inside a string literal), and the
  SQLite connection itself is opened read-only via `mode=ro` URI — so
  even a statement that somehow got past step 1 fails at the DB layer.
- **Schema is introspected, not hardcoded**: `schema.py` reads
  `PRAGMA table_info` / `PRAGMA foreign_key_list` at runtime, so the
  same pipeline works against any SQLite DB you point it at.
- **LLM response is validated with `pydantic`**, not parsed by hand —
  the expected JSON shape is declared once as a model
  (`ClarifierResult`), and a malformed response fails loudly at that
  boundary instead of causing an `AttributeError` somewhere downstream.

## Extending this

- Swap the sample SQLite DB for Postgres/MySQL (schema.py's SQL is
  SQLite-specific via `PRAGMA`; would need an equivalent
  `information_schema` query per dialect).
- Add a confidence score alongside `action` so borderline cases can be
  tuned via a threshold instead of a binary decision.
- Cache schema descriptions per DB instead of recomputing per session.
- Add a `explain` mode that shows the query plan alongside results.

## Files

- `data/generate_db.py` — builds the synthetic sample DB (customers,
  products, orders, order_items) with intentional ambiguity (two date
  columns, multiple status values) to demo the clarifier meaningfully.
  Uses `Faker` for names/emails and `pandas.to_sql` for bulk inserts.
- `core/schema.py` — schema + enum value-hint introspection.
- `core/llm_client.py` — thin Groq API wrapper (free tier), structured JSON parsing.
- `core/clarifier.py` — the clarification/generation decision logic,
  response shape validated with `pydantic`.
- `core/executor.py` — SELECT-only validation via `sqlglot`, safe
  read-only execution, results returned as a `pandas.DataFrame`.
- `app.py` — Streamlit chat UI.

## Libraries used and why

| Library | Replaces | Why |
|---|---|---|
| `sqlglot` | regex-based SQL keyword blocklist | Actually parses the SQL and checks it's a single `SELECT` statement — correct even when a string literal contains SQL-looking text, which a regex can't reliably tell apart from real injection. |
| `pandas` | manual cursor/row/column bookkeeping | `read_sql_query` returns a ready-to-display table; `to_sql` replaces manual `executemany` for seeding the sample DB. |
| `pydantic` | manual `dict.get()` parsing of the LLM's JSON response | Declares the expected response shape once (`ClarifierResult`); a malformed response fails loudly and clearly instead of silently producing `None`s. |
| `Faker` | hand-written name/email lists | Generates realistic, varied sample data with one call instead of maintaining static lists. |
