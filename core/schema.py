"""
Reads the SQLite schema and turns it into a compact text description
that we feed to the LLM as context (schema linking).
"""

import sqlite3


def get_schema_description(db_path: str) -> str:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [r[0] for r in cur.fetchall()]

    lines = []
    for table in tables:
        cur.execute(f"PRAGMA table_info({table})")
        cols = cur.fetchall()  # cid, name, type, notnull, dflt_value, pk
        col_descs = [f"{c[1]} {c[2]}{' PK' if c[5] else ''}" for c in cols]

        cur.execute(f"PRAGMA foreign_key_list({table})")
        fks = cur.fetchall()
        fk_descs = [f"{fk[3]} -> {fk[2]}.{fk[4]}" for fk in fks]

        # Sample distinct values for low-cardinality text columns — this is
        # what lets the model know e.g. status has 5 specific values, or
        # that 'region' means North/South/East/West, instead of guessing.
        enum_hints = []
        for c in cols:
            col_name, col_type = c[1], c[2].upper()
            if "CHAR" in col_type or "TEXT" in col_type:
                cur.execute(f"SELECT COUNT(DISTINCT {col_name}) FROM {table}")
                distinct_count = cur.fetchone()[0]
                if 0 < distinct_count <= 8:
                    cur.execute(f"SELECT DISTINCT {col_name} FROM {table} LIMIT 8")
                    vals = [str(r[0]) for r in cur.fetchall()]
                    enum_hints.append(f"{col_name} in {{{', '.join(vals)}}}")

        block = f"TABLE {table} ({', '.join(col_descs)})"
        if fk_descs:
            block += f"\n  foreign keys: {', '.join(fk_descs)}"
        if enum_hints:
            block += f"\n  value hints: {', '.join(enum_hints)}"
        lines.append(block)

    conn.close()
    return "\n\n".join(lines)
