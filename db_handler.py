# db_handler.py  – MySQL edition
import streamlit as st
import mysql.connector
from mysql.connector import OperationalError, InterfaceError   # reconnect check
import pandas as pd
import uuid

# ───────────────────────────────────────────────────────────────
# 1. One cached connection per user session
# ───────────────────────────────────────────────────────────────
def _session_key() -> str:
    """Return a unique key for the current user session."""
    if "_session_key" not in st.session_state:
        st.session_state["_session_key"] = uuid.uuid4().hex
    return st.session_state["_session_key"]


@st.cache_resource(show_spinner=False)
def get_conn(params: dict, key: str):
    """
    Create (once per session) and return a MySQL connection.
    `params` is the kwargs-dict you would normally pass to
    `mysql.connector.connect(**params)`.
    """
    conn = mysql.connector.connect(**params)
    try:
        st.on_session_end(conn.close)
    except Exception:
        pass
    return conn

# ───────────────────────────────────────────────────────────────
# 2. Database manager with auto-reconnect logic
# ───────────────────────────────────────────────────────────────
class DatabaseManager:
    """General DB interactions using a cached connection."""

    def __init__(self):
        # Credentials live in .streamlit/secrets.toml
        # Either top-level keys (DB_HOST …) *or* a [mysql] section work.
        secrets = st.secrets
        if "mysql" in secrets:
            secrets = secrets["mysql"]

        self.params = dict(
            host      = secrets["DB_HOST"],
            port      = int(secrets["DB_PORT"]),
            user      = secrets["DB_USER"],
            password  = secrets["DB_PASS"],
            database  = secrets["DB_NAME"],
            autocommit=True,
            charset   ="utf8mb4",
            collation ="utf8mb4_unicode_ci",
            raise_on_warnings=True,
        )
        self._key  = _session_key()
        self.conn  = get_conn(self.params, self._key)  # reuse within this session

    # ────────── internal helpers ──────────
    def _ensure_live_conn(self):
        """Reconnect if the cached connection was closed by MySQL."""
        if not self.conn.is_connected():       # False means closed
            get_conn.clear()
            self.conn = get_conn(self.params, self._key)

    def _fetch_df(self, query: str, params=None) -> pd.DataFrame:
        self._ensure_live_conn()
        try:  # first attempt
            with self.conn.cursor() as cur:
                cur.execute(query, params or ())
                rows = cur.fetchall()
                cols = [c[0] for c in cur.description]
        except (OperationalError, InterfaceError):
            get_conn.clear()
            self.conn = get_conn(self.params, self._key)
            with self.conn.cursor() as cur:
                cur.execute(query, params or ())
                rows = cur.fetchall()
                cols = [c[0] for c in cur.description]
        except Exception:
            self.conn.rollback()               # recover from broken tx
            raise
        return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame()

    def _execute(self, query: str, params=None, returning=False):
        """
        Run INSERT/UPDATE/DELETE.
        If `returning` is True **you must include your own SELECT** in `query`
        because MySQL’s `RETURNING` is limited.
        """
        self._ensure_live_conn()
        try:
            with self.conn.cursor() as cur:
                cur.execute(query, params or ())
                res = cur.fetchone() if returning else None
            self.conn.commit()
            return res
        except (OperationalError, InterfaceError):
            get_conn.clear()
            self.conn = get_conn(self.params, self._key)
            with self.conn.cursor() as cur:
                cur.execute(query, params or ())
                res = cur.fetchone() if returning else None
            self.conn.commit()
            return res
        except Exception:
            self.conn.rollback()
            raise

    # ────────── public API ──────────
    def fetch_data(self, query, params=None):
        return self._fetch_df(query, params)

    def execute_command(self, query, params=None):
        self._execute(query, params)

    def execute_command_returning(self, query, params=None):
        return self._execute(query, params, returning=True)

    # ─────────── Dropdown Management ───────────
    def get_all_sections(self):
        df = self.fetch_data("SELECT DISTINCT section FROM dropdowns")
        return df["section"].tolist()

    def get_dropdown_values(self, section):
        q = "SELECT value FROM dropdowns WHERE section = %s"
        df = self.fetch_data(q, (section,))
        return df["value"].tolist()

    # ─────────── Supplier Management ───────────
    def get_suppliers(self):
        return self.fetch_data(
            "SELECT supplierid, suppliername FROM supplier"
        )

    # ─────────── Inventory Management ───────────
    def add_inventory(self, data: dict):
        cols = ", ".join(data.keys())
        ph   = ", ".join(["%s"] * len(data))
        q = f"INSERT INTO inventory ({cols}) VALUES ({ph})"
        self.execute_command(q, list(data.values()))

    # ─────────── foreign_key Management ───────────
    def check_foreign_key_references(
        self,
        referenced_table: str,
        referenced_column: str,
        value
    ) -> list[str]:
        """
        Return tables that still reference `value` via FOREIGN KEY.
        Empty list ⇒ safe to delete.
        """
        # 1️⃣  find all foreign-key constraints that target the PK
        fk_sql = """
            SELECT tc.table_schema,
                   tc.table_name
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

        conflicts: list[str] = []
        for _, row in fks.iterrows():
            schema = row["table_schema"]
            table  = row["table_name"]

            # 2️⃣  check if at least one record references the value
            exists_sql = f"""
                SELECT EXISTS(
                    SELECT 1
                    FROM   `{schema}`.`{table}`
                    WHERE  {referenced_column} = %s
                );
            """
            exists = self.fetch_data(exists_sql, (value,)).iat[0, 0]
            if exists:
                conflicts.append(f"{schema}.{table}")

        return sorted(set(conflicts))
