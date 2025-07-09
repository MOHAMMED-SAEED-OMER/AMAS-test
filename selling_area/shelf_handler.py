"""
db_handler.py  – PostgreSQL/Neon edition (psycopg 3 driver, no native crashes)

Compared with the old MySQL-based version
──────────────────────────────────────────
• Uses **psycopg 3** (pure-Python) – lighter than psycopg2 and fully async-ready.
• One cached connection per Streamlit session (`st.cache_resource`).
• Automatic keep-alive: a cheap `SELECT 1` (or reconnect) before every query
  prevents “connection closed” errors when Neon pauses an idle session.
• Public API and helper names are **unchanged**, so the rest of your codebase
  (e.g. `ShelfHandler`, Supplier pages, etc.) can stay as-is.
"""

from __future__ import annotations

import uuid
from typing import Any, Sequence, List

import pandas as pd
import psycopg                           # psycopg 3
from psycopg.rows import dict_row        # rows → dict for painless DF build
import streamlit as st

# ─────────────────────────────────────────────────────────────
# 1. Helpers for session-scoped connection
# ─────────────────────────────────────────────────────────────
def _session_key() -> str:
    """Unique key per Streamlit browser session."""
    if "_session_key" not in st.session_state:
        st.session_state["_session_key"] = uuid.uuid4().hex
    return st.session_state["_session_key"]


@st.cache_resource(show_spinner=False)
def _get_conn(params: dict, cache_key: str) -> psycopg.Connection:
    """Create a psycopg 3 connection once per Streamlit session."""
    conn = psycopg.connect(**params, row_factory=dict_row, autocommit=True)
    try:
        st.on_session_end(conn.close)    # tidy shutdown in the browser tab
    except Exception:                    # running in a non-interactive context
        pass
    return conn


# ─────────────────────────────────────────────────────────────
# 2. DatabaseManager
# ─────────────────────────────────────────────────────────────
class DatabaseManager:
    """Lightweight DB helper using a cached psycopg 3 connection."""

    def __init__(self) -> None:
        # ---- read secrets ---------------------------------------------------
        secrets = st.secrets
        if "postgres" in secrets:                 # allow sectioned [postgres]
            secrets = secrets["postgres"]

        def pick(*keys: str, default: Any = None):
            """Return first present secret key (case-insensitive)."""
            for k in keys:
                for variant in (k, k.lower()):
                    if variant in secrets:
                        return secrets[variant]
            return default

        self._params: dict[str, Any] = dict(
            host       = pick("DB_HOST",  "host"),
            port       = int(pick("DB_PORT", "port", default=5432)),
            dbname     = pick("DB_NAME",  "database"),
            user       = pick("DB_USER",  "user"),
            password   = pick("DB_PASS",  "password"),
            sslmode    = pick("DB_SSLMODE", "sslmode", default="require"),
            # Neon expects SSL; `require` is safest.
        )

        self._cache_key = _session_key()
        self.conn       = _get_conn(self._params, self._cache_key)

    # ---------- internal util ----------------------------------------------
    def _ensure_live(self) -> None:
        """Make sure the connection is open; reconnect if Neon suspended it."""
        try:
            if self.conn.closed:                       # type: ignore[attr-defined]
                raise psycopg.OperationalError
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1;")
        except Exception:
            _get_conn.clear()                          # bust Streamlit cache
            self.conn = _get_conn(self._params, self._cache_key)

    def _fetch_df(
        self,
        sql: str,
        params: Sequence[Any] | None = None
    ) -> pd.DataFrame:
        self._ensure_live()
        with self.conn.cursor() as cur:
            cur.execute(sql, params or ())
            rows = cur.fetchall()
            if not rows:               # empty result → empty DF with 0 columns
                return pd.DataFrame()
            return pd.DataFrame(rows)  # dict_row → keys become columns

    def _execute(
        self,
        sql: str,
        params: Sequence[Any] | None = None,
        *,
        returning: bool = False
    ):
        self._ensure_live()
        with self.conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchone() if returning else None

    # ---------- public API --------------------------------------------------
    def fetch_data(
        self,
        query: str,
        params: Sequence[Any] | None = None
    ) -> pd.DataFrame:
        return self._fetch_df(query, params)

    def execute_command(
        self,
        query: str,
        params: Sequence[Any] | None = None
    ) -> None:
        self._execute(query, params)

    def execute_command_returning(
        self,
        query: str,
        params: Sequence[Any] | None = None,
    ):
        return self._execute(query, params, returning=True)

    # ---------- Dropdown helpers -------------------------------------------
    def get_all_sections(self) -> List[str]:
        df = self.fetch_data("SELECT DISTINCT section FROM dropdowns;")
        return df["section"].tolist()

    def get_dropdown_values(self, section: str) -> List[str]:
        df = self.fetch_data(
            "SELECT value FROM dropdowns WHERE section = %s;", (section,)
        )
        return df["value"].tolist()

    # ---------- Supplier helpers -------------------------------------------
    def get_suppliers(self) -> pd.DataFrame:
        return self.fetch_data(
            "SELECT supplierid, suppliername FROM supplier;"
        )

    # ---------- Inventory helpers ------------------------------------------
    def add_inventory(self, data: dict[str, Any]) -> None:
        cols = ", ".join(data.keys())
        ph   = ", ".join(["%s"] * len(data))
        q    = f"INSERT INTO inventory ({cols}) VALUES ({ph});"
        self.execute_command(q, list(data.values()))

    # ---------- FK safety helper -------------------------------------------
    def check_foreign_key_references(
        self,
        referenced_table: str,
        referenced_column: str,
        value: Any
    ) -> List[str]:
        fk_sql = """
            SELECT tc.table_schema, tc.table_name
            FROM   information_schema.table_constraints AS tc
            JOIN   information_schema.key_column_usage AS kcu
                   ON tc.constraint_name = kcu.constraint_name
            JOIN   information_schema.constraint_column_usage AS ccu
                   ON ccu.constraint_name = tc.constraint_name
            WHERE  tc.constraint_type = 'FOREIGN KEY'
              AND  ccu.table_name      = %s
              AND  ccu.column_name     = %s;
        """
        fks = self.fetch_data(fk_sql, (referenced_table, referenced_column))

        conflicts: List[str] = []
        for _, row in fks.iterrows():
            schema = row["table_schema"]
            table  = row["table_name"]
            exists_sql = f"""
                SELECT EXISTS(
                    SELECT 1
                    FROM   {schema}.{table}
                    WHERE  {referenced_column} = %s
                );
            """
            exists = self.fetch_data(exists_sql, (value,)).iat[0, 0]
            if exists:
                conflicts.append(f"{schema}.{table}")

        return sorted(set(conflicts))
