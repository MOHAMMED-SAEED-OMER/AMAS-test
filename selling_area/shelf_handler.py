"""
db_handler.py  – MySQL edition, PyMySQL driver (no native crashes)

Why the rewrite?
────────────────
• mysql-connector-python links against glibc/openssl and can corrupt the
  heap on Alpine-based containers → “malloc(): unsorted double linked list
  corrupted”.  Switching to **PyMySQL** avoids native code entirely.

Key points
──────────
• One cached PyMySQL connection per Streamlit session (st.cache_resource).
• Automatic keep-alive: conn.ping(reconnect=True) before each query avoids
  the “MySQL server has gone away” error.
• Public API identical to the old version (fetch_data, execute_command,
  execute_command_returning, etc.).
"""

from __future__ import annotations

import uuid
from typing import Any, Sequence, List

import pandas as pd
import pymysql
from pymysql.err import OperationalError, InterfaceError
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
def _get_conn(params: dict, cache_key: str):
    """Create a PyMySQL connection once per session."""
    conn = pymysql.connect(**params)
    try:
        st.on_session_end(conn.close)
    except Exception:  # running outside interactive session
        pass
    return conn

# ─────────────────────────────────────────────────────────────
# 2. DatabaseManager
# ─────────────────────────────────────────────────────────────
class DatabaseManager:
    """Lightweight DB helper using a cached PyMySQL connection."""

    def __init__(self):
        # ---- read secrets ---------------------------------------------------
        secrets = st.secrets
        if "mysql" in secrets:           # sectioned secrets.toml
            secrets = secrets["mysql"]

        def pick(*keys, default=None):
            """Return first present secret key (case-insensitive)."""
            for k in keys:
                try:
                    return secrets[k]
                except KeyError:
                    try:
                        return secrets[k.lower()]  # allow lower-case
                    except KeyError:
                        continue
            return default

        self._params: dict[str, Any] = dict(
            host            = pick("DB_HOST", "host"),
            port            = int(pick("DB_PORT", "port", default=3306)),
            user            = pick("DB_USER", "user"),
            password        = pick("DB_PASS", "password"),
            database        = pick("DB_NAME", "database"),
            charset         = "utf8mb4",
            autocommit      = True,
            cursorclass     = pymysql.cursors.Cursor,  # plain tuples
        )

        self._cache_key = _session_key()
        self.conn       = _get_conn(self._params, self._cache_key)

    # ---------- internal util ----------------------------------------------
    def _ensure_live(self):
        """Ping connection; reconnect if server closed it."""
        try:
            self.conn.ping(reconnect=True)
        except Exception:
            _get_conn.clear()
            self.conn = _get_conn(self._params, self._cache_key)

    def _fetch_df(self, sql: str, params: Sequence[Any] | None = None) -> pd.DataFrame:
        self._ensure_live()
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql, params or ())
                rows = cur.fetchall()
                cols = [c[0] for c in cur.description]
            return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame()
        except (OperationalError, InterfaceError):
            # retry once after reconnect
            _get_conn.clear()
            self.conn = _get_conn(self._params, self._cache_key)
            with self.conn.cursor() as cur:
                cur.execute(sql, params or ())
                rows = cur.fetchall()
                cols = [c[0] for c in cur.description]
            return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame()

    def _execute(self, sql: str, params: Sequence[Any] | None = None, *, returning=False):
        self._ensure_live()
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql, params or ())
                result = cur.fetchone() if returning else None
            return result
        except (OperationalError, InterfaceError):
            _get_conn.clear()
            self.conn = _get_conn(self._params, self._cache_key)
            with self.conn.cursor() as cur:
                cur.execute(sql, params or ())
                result = cur.fetchone() if returning else None
            return result

    # ---------- public API --------------------------------------------------
    def fetch_data(self, query: str, params: Sequence[Any] | None = None) -> pd.DataFrame:
        return self._fetch_df(query, params)

    def execute_command(self, query: str, params: Sequence[Any] | None = None) -> None:
        self._execute(query, params)

    def execute_command_returning(
        self, query: str, params: Sequence[Any] | None = None
    ):
        return self._execute(query, params, returning=True)

    # ---------- Dropdown helpers -------------------------------------------
    def get_all_sections(self) -> List[str]:
        df = self.fetch_data("SELECT DISTINCT section FROM dropdowns")
        return df["section"].tolist()

    def get_dropdown_values(self, section: str) -> List[str]:
        df = self.fetch_data("SELECT value FROM dropdowns WHERE section = %s", (section,))
        return df["value"].tolist()

    # ---------- Supplier helpers -------------------------------------------
    def get_suppliers(self) -> pd.DataFrame:
        return self.fetch_data("SELECT supplierid, suppliername FROM supplier")

    # ---------- Inventory helpers ------------------------------------------
    def add_inventory(self, data: dict[str, Any]) -> None:
        cols = ", ".join(data.keys())
        ph   = ", ".join(["%s"] * len(data))
        q = f"INSERT INTO inventory ({cols}) VALUES ({ph})"
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
