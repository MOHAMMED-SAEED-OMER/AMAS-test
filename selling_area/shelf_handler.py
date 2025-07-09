"""
selling_area/shelf_handler.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Database helper for Selling-Area “Shelf” pages (Streamlit 1.46+).

✅  Postgres / Neon-ready   ✅  Thread-safe   ✅  Connection-pooled
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Iterable, Sequence

import pandas as pd
import psycopg_pool
import streamlit as st

# ────────────────────────────────────────────────────────────────
# 0.  Connection pool (cached across Streamlit reruns)
# ────────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def _get_pool() -> psycopg_pool.ConnectionPool:
    """
    One global pool per Streamlit worker process.
    Adjust min_size / max_size to match your Neon plan.
    """
    return psycopg_pool.ConnectionPool(
        conninfo=st.secrets["postgres_url"],
        min_size=1,
        max_size=10,
        # Clean idle conns quickly so Community Cloud's 1 GB limit is safe
        max_idle=_dt.timedelta(minutes=5),
        timeout=_dt.timedelta(seconds=30),
    )


# ────────────────────────────────────────────────────────────────
# 1.  Lightweight DB wrapper
# ────────────────────────────────────────────────────────────────
class DatabaseManager:
    """Tiny helper around psycopg-pool for Pandas-friendly I/O."""

    # Helpers -----------------------------------------------------
    def _conn(self):
        """Short-lived dedicated connection for the current thread."""
        return _get_pool().connection()

    # high-volume reads ------------------------------------------
    def fetch_data(
        self, sql: str, params: Sequence[Any] | None = None
    ) -> pd.DataFrame:  # noqa: D401
        with self._conn() as conn:  # auto-commit OFF inside context
            df = pd.read_sql(sql, conn, params=params)
        return df

    # low-volume writes / DDL ------------------------------------
    def execute_command(
        self, sql: str, params: Sequence[Any] | None = None
    ) -> None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)


# ────────────────────────────────────────────────────────────────
# 2.  Shelf-specific helpers
# ────────────────────────────────────────────────────────────────
class ShelfHandler(DatabaseManager):
    """All database helpers for the Selling-Area shelf."""

    # ────────────────────────────────────────────────────────────
    # 2.1  Current shelf contents
    # ────────────────────────────────────────────────────────────
    @st.cache_data(ttl=10)  # refresh at most once every 10 s
    def get_shelf_items(self) -> pd.DataFrame:
        return self.fetch_data(
            """
            SELECT s.shelfid,
                   s.itemid,
                   i.itemnameenglish        AS itemname,
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
              AND  locid IS NOT NULL
            ORDER  BY entrydate DESC
            LIMIT 1
            """,
            (itemid,),
        )
        return None if df.empty else str(df.iloc[0, 0])

    # ────────────────────────────────────────────────────────────
    # 2.3  Insert / increment shelf row  +  movement log
    # ────────────────────────────────────────────────────────────
    def add_to_shelf(
        self,
        *,
        itemid: int,
        expirationdate,  # date or ISO str; psycopg will adapt
        quantity: int,
        created_by: str,
        cost_per_unit: float,
        locid: str,
    ) -> None:
        """
        Upsert a shelf row (unique on item+expiry+cost) **and**
        write to `shelfentries`. All wrapped in one transaction.
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                # 1️⃣  Upsert shelf row
                cur.execute(
                    """
                    INSERT INTO shelf (itemid, expirationdate, quantity,
                                       cost_per_unit, locid)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (itemid, expirationdate, cost_per_unit)
                    DO UPDATE
                      SET quantity      = shelf.quantity + EXCLUDED.quantity,
                          cost_per_unit = EXCLUDED.cost_per_unit,
                          locid         = EXCLUDED.locid,
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

                # 2️⃣  Movement log
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
            # leaving the `with conn:` block commits the transaction

    # ────────────────────────────────────────────────────────────
    # 2.4  Inventory helper (barcode lookup)
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
        Consume the oldest open shortages for *itemid* up to *qty_need*.
        Returns how many units still need to be placed on shelf afterwards.
        """
        remaining = qty_need

        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT shortageid, shortage_qty
                    FROM   shelf_shortage
                    WHERE  itemid = %s
                      AND  resolved = FALSE
                    ORDER  BY logged_at
                    FOR UPDATE
                    """,
                    (itemid,),
                )
                rows = cur.fetchall()

                for shortageid, shortage_qty in rows:
                    if remaining == 0:
                        break
                    take = min(remaining, shortage_qty)

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
                        (take, take, take, take, user, shortageid),
                    )
                    remaining -= take

                # tidy up zero-quantity rows
                cur.execute(
                    "DELETE FROM shelf_shortage WHERE shortage_qty = 0"
                )

        return remaining

    # ────────────────────────────────────────────────────────────
    # 2.6  Quick low-stock query
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
            df["shelfaverage"] = df["shelfaverage"].astype("Int64")
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
            df["totalquantity"] = df["totalquantity"].astype(int)
            df["shelfthreshold"] = df["shelfthreshold"].astype("Int64")
            df["shelfaverage"] = df["shelfaverage"].astype("Int64")
        return df
