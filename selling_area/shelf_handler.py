"""
selling_area/shelf_handler.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Database helpers for the Selling-Area “Shelf” pages (MySQL 8.0).

Key points
──────────
• Uses a single `MySQLConnectionPool` cached with `@st.cache_resource`
  → avoids connection storms when Streamlit reruns rapidly.
• Each method grabs a short-lived connection (`pool.get_connection()`)
  and closes it in a `finally:` block (thread-safe, no leaks).
• All writes are done inside one explicit transaction; partial errors
  roll back automatically.
• Frequently-called read queries are memoised with `@st.cache_data`
  (TTL 10-30 s) to cut latency during UI spam-clicks.
"""

from __future__ import annotations

from contextlib import closing
from typing import Any, Sequence, List, Dict

import pandas as pd
import streamlit as st
import mysql.connector
import mysql.connector.pooling


# ────────────────────────────────────────────────────────────────
# 0   Connection pool (cached across Streamlit reruns)
# ────────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def _get_pool() -> mysql.connector.pooling.MySQLConnectionPool:
    """One global pool per worker process (adjust pool_size as needed)."""
    return mysql.connector.pooling.MySQLConnectionPool(
        pool_name="amas_pool",
        pool_size=10,
        pool_reset_session=True,  # clean session vars & temp tables
        host=st.secrets["mysql"]["host"],
        user=st.secrets["mysql"]["user"],
        password=st.secrets["mysql"]["password"],
        database=st.secrets["mysql"]["database"],
        autocommit=False,         # we control commit/rollback
        connection_timeout=30,
    )


# ────────────────────────────────────────────────────────────────
# 1   Thin wrapper for Pandas-friendly I/O
# ────────────────────────────────────────────────────────────────
class DatabaseManager:
    """Helpers around mysql-connector with clean close/commit semantics."""

    # ---------- READS ---------- #
    def fetch_data(
        self, sql: str, params: Sequence[Any] | None = None
    ) -> pd.DataFrame:
        conn = _get_pool().get_connection()
        try:
            df = pd.read_sql(sql, conn, params=params)
        finally:
            conn.close()
        return df

    # ---------- WRITES ---------- #
    def execute_command(
        self, sql: str, params: Sequence[Any] | None = None
    ) -> None:
        conn = _get_pool().get_connection()
        try:
            with closing(conn.cursor()) as cur:
                cur.execute(sql, params)
            conn.commit()
        finally:
            conn.close()


# ────────────────────────────────────────────────────────────────
# 2   Shelf-specific helpers  (MySQL syntax)
# ────────────────────────────────────────────────────────────────
class ShelfHandler(DatabaseManager):
    """All DB helpers used by the Selling-Area shelf workflow."""

    # ────────────────────────────────────────────────────────────
    # 2.1  Current shelf contents
    # ────────────────────────────────────────────────────────────
    @st.cache_data(ttl=10)
    def get_shelf_items(self) -> pd.DataFrame:
        return self.fetch_data(
            """
            SELECT s.shelfid,
                   s.itemid,
                   i.itemnameenglish AS itemname,
                   s.quantity,
                   s.expirationdate,
                   s.cost_per_unit,
                   s.locid,
                   s.lastupdated
            FROM   shelf s
            JOIN   item  i ON s.itemid = i.itemid
            ORDER  BY i.itemnameenglish, s.expirationdate
            """
        )

    # ────────────────────────────────────────────────────────────
    # 2.2  Last used shelf location
    # ────────────────────────────────────────────────────────────
    def last_locid(self, itemid: int) -> str | None:
        df = self.fetch_data(
            """
            SELECT locid
            FROM   shelfentries
            WHERE  itemid = %s
              AND  locid  IS NOT NULL
            ORDER  BY entrydate DESC
            LIMIT 1
            """,
            (itemid,),
        )
        return None if df.empty else str(df.iloc[0, 0])

    # ────────────────────────────────────────────────────────────
    # 2.3  Upsert shelf row + movement log (transactional)
    # ────────────────────────────────────────────────────────────
    def add_to_shelf(
        self,
        *,
        itemid: int,
        expirationdate,
        quantity: int,
        created_by: str,
        cost_per_unit: float,
        locid: str,
    ) -> None:
        conn = _get_pool().get_connection()
        try:
            with closing(conn.cursor()) as cur:
                # 1️⃣  Upsert / increment existing shelf row
                cur.execute(
                    """
                    INSERT INTO shelf (itemid, expirationdate, quantity,
                                       cost_per_unit, locid)
                    VALUES (%s, %s, %s, %s, %s) AS new
                    ON DUPLICATE KEY UPDATE
                        quantity      = shelf.quantity + new.quantity,
                        cost_per_unit = new.cost_per_unit,
                        locid         = new.locid,
                        lastupdated   = CURRENT_TIMESTAMP
                    """,
                    (
                        itemid,
                        expirationdate,
                        int(quantity),
                        float(cost_per_unit),
                        locid,
                    ),
                )

                # 2️⃣  Movement log (always append)
                cur.execute(
                    """
                    INSERT INTO shelfentries
                           (itemid, expirationdate, quantity,
                            cost_per_unit, createdby, locid)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        itemid,
                        expirationdate,
                        int(quantity),
                        float(cost_per_unit),
                        created_by,
                        locid,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    # ────────────────────────────────────────────────────────────
    # 2.4  Inventory helper (barcode → layers)
    # ────────────────────────────────────────────────────────────
    def get_inventory_by_barcode(self, barcode: str) -> pd.DataFrame:
        return self.fetch_data(
            """
            SELECT inv.itemid,
                   i.itemnameenglish AS itemname,
                   inv.quantity,
                   inv.expirationdate,
                   inv.cost_per_unit
            FROM   inventory inv
            JOIN   item       i ON inv.itemid = i.itemid
            WHERE  i.barcode = %s
              AND  inv.quantity > 0
            ORDER  BY inv.expirationdate
            """,
            (barcode,),
        )

    # ────────────────────────────────────────────────────────────
    # 2.5  Shortage resolver
    # ────────────────────────────────────────────────────────────
    def resolve_shortages(
        self, *, itemid: int, qty_need: int, user: str
    ) -> int:
        """
        Consume open shortages for *itemid* (oldest first) up to *qty_need*.
        Returns remaining units that still need to be placed on shelf.
        """
        remaining = qty_need
        conn = _get_pool().get_connection()
        try:
            with closing(conn.cursor(dictionary=True)) as cur:
                # Lock rows so concurrent transfers don’t step on each other
                cur.execute(
                    """
                    SELECT shortageid, shortage_qty
                    FROM   shelf_shortage
                    WHERE  itemid   = %s
                      AND  resolved = FALSE
                    ORDER  BY logged_at
                    FOR UPDATE
                    """,
                    (itemid,),
                )
                rows: List[Dict[str, Any]] = cur.fetchall()

                for row in rows:
                    if remaining == 0:
                        break
                    take = min(remaining, int(row["shortage_qty"]))

                    cur.execute(
                        """
                        UPDATE shelf_shortage
                        SET shortage_qty = shortage_qty - %s,
                            resolved      = (shortage_qty - %s = 0),
                            resolved_qty  = COALESCE(resolved_qty,0) + %s,
                            resolved_at   = CASE
                                               WHEN shortage_qty - %s = 0
                                               THEN CURRENT_TIMESTAMP
                                            END,
                            resolved_by   = %s
                        WHERE shortageid = %s
                        """,
                        (
                            take,
                            take,
                            take,
                            take,
                            user,
                            row["shortageid"],
                        ),
                    )
                    remaining -= take

                # Tidy any zero-qty rows
                cur.execute("DELETE FROM shelf_shortage WHERE shortage_qty = 0")
            conn.commit()
        finally:
            conn.close()

        return remaining

    # ────────────────────────────────────────────────────────────
    # 2.6  Quick low-stock query (Alerts tab)
    # ────────────────────────────────────────────────────────────
    @st.cache_data(ttl=10)
    def get_low_shelf_stock(self, threshold: int = 10) -> pd.DataFrame:
        return self.fetch_data(
            """
            SELECT s.itemid,
                   i.itemnameenglish AS itemname,
                   s.quantity,
                   s.expirationdate
            FROM   shelf s
            JOIN   item  i ON s.itemid = i.itemid
            WHERE  s.quantity <= %s
            ORDER  BY s.quantity ASC
            """,
            (threshold,),
        )

    # ────────────────────────────────────────────────────────────
    # 2.7  Master item list (Manage-Settings tab)
    # ────────────────────────────────────────────────────────────
    @st.cache_data(ttl=30)
    def get_all_items(self) -> pd.DataFrame:
        df = self.fetch_data(
            """
            SELECT itemid,
                   itemnameenglish AS itemname,
                   shelfthreshold,
                   shelfaverage
            FROM   item
            ORDER  BY itemnameenglish
            """
        )
        if not df.empty:
            df["shelfthreshold"] = df["shelfthreshold"].astype("Int64")
            df["shelfaverage"]   = df["shelfaverage"].astype("Int64")
        return df

    def update_shelf_settings(self, itemid: int, thr: int, avg: int) -> None:
        self.execute_command(
            """
            UPDATE item
            SET    shelfthreshold = %s,
                   shelfaverage   = %s
            WHERE  itemid = %s
            """,
            (int(thr), int(avg), int(itemid)),
        )

    # ────────────────────────────────────────────────────────────
    # 2.8  Quantity-by-item (Alerts tab)
    # ────────────────────────────────────────────────────────────
    @st.cache_data(ttl=10)
    def get_shelf_quantity_by_item(self) -> pd.DataFrame:
        df = self.fetch_data(
            """
            SELECT i.itemid,
                   i.itemnameenglish AS itemname,
                   COALESCE(SUM(s.quantity), 0) AS totalquantity,
                   i.shelfthreshold,
                   i.shelfaverage
            FROM   item  i
            LEFT JOIN shelf s ON i.itemid = s.itemid
            GROUP  BY i.itemid, i.itemnameenglish,
                     i.shelfthreshold, i.shelfaverage
            ORDER  BY i.itemnameenglish
            """
        )
        if not df.empty:
            df["totalquantity"]  = df["totalquantity"].astype(int)
            df["shelfthreshold"] = df["shelfthreshold"].astype("Int64")
            df["shelfaverage"]   = df["shelfaverage"].astype("Int64")
        return df
