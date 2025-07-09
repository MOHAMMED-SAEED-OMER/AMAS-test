"""
selling_area/shelf_handler.py
─────────────────────────────
MySQL 8.0 helper — concise, resilient, and no infinite reruns.
"""

from __future__ import annotations

import time
from contextlib import closing
from typing import Any, Sequence

import pandas as pd
import streamlit as st
import mysql.connector
import mysql.connector.pooling
from mysql.connector import errors as sqlerr


# ╭────────────────────────────────────────────────────────────╮
# │ 0.  Connection helper                                      │
# ╰────────────────────────────────────────────────────────────╯
@st.cache_resource(show_spinner=False)
def _get_pool() -> mysql.connector.pooling.MySQLConnectionPool | None:
    """Try to build a tiny pool once; return None if DB unreachable."""
    cfg = {
        "host":     st.secrets["mysql"]["host"],
        "port":     int(st.secrets["mysql"].get("port", 3306)),
        "user":     st.secrets["mysql"]["user"],
        "password": st.secrets["mysql"]["password"],
        "database": st.secrets["mysql"]["database"],
        "autocommit": False,
        "connection_timeout": 5,
    }
    try:
        return mysql.connector.pooling.MySQLConnectionPool(
            pool_name="amas_pool", pool_size=2,
            pool_reset_session=True, **cfg
        )
    except sqlerr.InterfaceError as e:
        st.error(f"❌ Cannot reach MySQL: {e.msg}")
        return None


def _safe_conn(retries: int = 2):
    """Get a connection or raise after a couple of quick retries."""
    pool = _get_pool()
    if pool is None:
        raise RuntimeError("Database unreachable")
    last: Exception | None = None
    for back in range(retries + 1):
        try:
            return pool.get_connection()
        except sqlerr.InterfaceError as err:
            last = err
            time.sleep(back)      # 0 s → 1 s
    raise last


# ╭────────────────────────────────────────────────────────────╮
# │ 1.  Thin wrapper                                           │
# ╰────────────────────────────────────────────────────────────╯
class DatabaseManager:
    def fetch_data(
        self, sql: str, params: Sequence[Any] | None = None
    ) -> pd.DataFrame:
        conn = _safe_conn()
        try:
            return pd.read_sql(sql, conn, params=params)
        finally:
            conn.close()

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> None:
        conn = _safe_conn()
        try:
            with closing(conn.cursor()) as cur:
                cur.execute(sql, params)
            conn.commit()
        finally:
            conn.close()


# ╭────────────────────────────────────────────────────────────╮
# │ 2.  Shelf-specific helpers                                 │
# ╰────────────────────────────────────────────────────────────╯
class ShelfHandler(DatabaseManager):

    # ── 2.1 current shelf items ──────────────────────────────
    @st.cache_data(ttl=10)
    def get_shelf_items(_self) -> pd.DataFrame:
        return _self.fetch_data(
            """
            SELECT s.shelfid, s.itemid, i.itemnameenglish AS itemname,
                   s.quantity, s.expirationdate, s.cost_per_unit,
                   s.locid, s.lastupdated
            FROM   shelf s
            JOIN   item  i ON s.itemid = i.itemid
            ORDER  BY i.itemnameenglish, s.expirationdate
            """
        )

    # ── 2.2 last locid helper ────────────────────────────────
    def last_locid(self, itemid: int) -> str | None:
        df = self.fetch_data(
            """
            SELECT locid FROM shelfentries
            WHERE itemid=%s AND locid IS NOT NULL
            ORDER BY entrydate DESC LIMIT 1
            """, (itemid,)
        )
        return None if df.empty else str(df.iloc[0, 0])

    # ── 2.3 add / increment shelf + log + inventory subtract ─
    def add_to_shelf(
        self, *, itemid: int, expirationdate, quantity: int,
        created_by: str, cost_per_unit: float, locid: str
    ) -> None:
        conn = _safe_conn()
        try:
            with closing(conn.cursor()) as cur:

                # ① shelf upsert
                cur.execute(
                    """
                    INSERT INTO shelf (itemid, expirationdate, quantity,
                                       cost_per_unit, locid)
                    VALUES (%s,%s,%s,%s,%s) AS new
                    ON DUPLICATE KEY UPDATE
                        quantity      = shelf.quantity + new.quantity,
                        cost_per_unit = new.cost_per_unit,
                        locid         = new.locid,
                        lastupdated   = CURRENT_TIMESTAMP
                    """,
                    (itemid, expirationdate, int(quantity),
                     float(cost_per_unit), locid)
                )

                # ② movement log
                cur.execute(
                    """
                    INSERT INTO shelfentries
                           (itemid, expirationdate, quantity,
                            cost_per_unit, createdby, locid)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    """,
                    (itemid, expirationdate, int(quantity),
                     float(cost_per_unit), created_by, locid)
                )

                # ③ inventory decrement
                cur.execute(
                    """
                    UPDATE inventory
                    SET quantity = quantity - %s
                    WHERE itemid=%s
                      AND expirationdate=%s
                      AND cost_per_unit = %s
                    """,
                    (int(quantity), itemid, expirationdate,
                     float(cost_per_unit))
                )
            conn.commit()
        finally:
            conn.close()

    # ── 2.4 inventory lookup ─────────────────────────────────
    def get_inventory_by_barcode(self, barcode: str) -> pd.DataFrame:
        return self.fetch_data(
            """
            SELECT inv.itemid, i.itemnameenglish AS itemname,
                   inv.quantity, inv.expirationdate, inv.cost_per_unit
            FROM   inventory inv
            JOIN   item i ON inv.itemid = i.itemid
            WHERE  i.barcode=%s AND inv.quantity > 0
            ORDER  BY inv.expirationdate
            """, (barcode,)
        )

    # ── 2.5 shortage resolver (unchanged logic) ──────────────
    def resolve_shortages(
        self, *, itemid: int, qty_need: int, user: str
    ) -> int:
        remaining = qty_need
        conn = _safe_conn()
        try:
            with closing(conn.cursor(dictionary=True)) as cur:
                cur.execute(
                    """
                    SELECT shortageid, shortage_qty
                    FROM   shelf_shortage
                    WHERE  itemid=%s AND resolved=FALSE
                    ORDER  BY logged_at FOR UPDATE
                    """, (itemid,)
                )
                for row in cur.fetchall():
                    if remaining == 0:
                        break
                    take = min(remaining, int(row["shortage_qty"]))
                    cur.execute(
                        """
                        UPDATE shelf_shortage
                        SET shortage_qty = shortage_qty - %s,
                            resolved      = (shortage_qty - %s = 0),
                            resolved_qty  = COALESCE(resolved_qty,0)+%s,
                            resolved_at   = CASE
                                             WHEN shortage_qty - %s = 0
                                             THEN CURRENT_TIMESTAMP END,
                            resolved_by   = %s
                        WHERE shortageid = %s
                        """,
                        (take, take, take, take, user, row["shortageid"])
                    )
                    remaining -= take
                cur.execute("DELETE FROM shelf_shortage WHERE shortage_qty = 0")
            conn.commit()
        finally:
            conn.close()
        return remaining

    # ── 2.6  quick low stock ─────────────────────────────────
    @st.cache_data(ttl=10)
    def get_low_shelf_stock(_self, threshold: int = 10):
        return _self.fetch_data(
            """
            SELECT s.itemid, i.itemnameenglish AS itemname,
                   s.quantity, s.expirationdate
            FROM   shelf s JOIN item i ON s.itemid = i.itemid
            WHERE  s.quantity <= %s
            ORDER  BY s.quantity
            """, (threshold,)
        )

    # ── 2.7  item master list ────────────────────────────────
    @st.cache_data(ttl=30)
    def get_all_items(_self):
        df = _self.fetch_data(
            """
            SELECT itemid, itemnameenglish AS itemname,
                   shelfthreshold, shelfaverage
            FROM   item ORDER BY itemnameenglish
            """
        )
        if not df.empty:
            df["shelfthreshold"] = df["shelfthreshold"].astype("Int64")
            df["shelfaverage"]   = df["shelfaverage"].astype("Int64")
        return df

    def update_shelf_settings(self, itemid: int, thr: int, avg: int) -> None:
        self.execute(
            """
            UPDATE item
            SET shelfthreshold=%s, shelfaverage=%s
            WHERE itemid=%s
            """, (int(thr), int(avg), int(itemid))
        )

    # ── 2.8  quantity by item ────────────────────────────────
    @st.cache_data(ttl=10)
    def get_shelf_quantity_by_item(_self):
        df = _self.fetch_data(
            """
            SELECT i.itemid, i.itemnameenglish AS itemname,
                   COALESCE(SUM(s.quantity),0) AS totalquantity,
                   i.shelfthreshold, i.shelfaverage
            FROM   item i
            LEFT JOIN shelf s ON i.itemid = s.itemid
            GROUP BY i.itemid, i.itemnameenglish,
                     i.shelfthreshold, i.shelfaverage
            ORDER BY i.itemnameenglish
            """
        )
        if not df.empty:
            df["totalquantity"]  = df["totalquantity"].astype(int)
            df["shelfthreshold"] = df["shelfthreshold"].astype("Int64")
            df["shelfaverage"]   = df["shelfaverage"].astype("Int64")
        return df
