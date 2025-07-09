"""
selling_area/shelf_handler.py
─────────────────────────────
Single-engine MySQL helper + optional debug cockpit.

Enable debug:
──────────────
• In .streamlit/secrets.toml
    [mysql]
    host = "…"
    user = "…"
    password = "…"
    database = "…"
    debug_sql = true         # 👈 add this
or
• Set env var AMAS_DEBUG_SQL=1 before launching Streamlit.
"""

from __future__ import annotations

import os
import time
from typing import Any, Sequence, Callable, TypeVar

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError, InterfaceError, SQLAlchemyError

# ── Debug flag ───────────────────────────────────────────────
DEBUG = (
    bool(os.getenv("AMAS_DEBUG_SQL"))
    or bool(st.secrets["mysql"].get("debug_sql", False))
)

# ── Engine setup ────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def _get_engine() -> Engine:
    cfg = st.secrets["mysql"]
    uri = (
        "mysql+mysqlconnector://"
        f"{cfg['user']}:{cfg['password']}@{cfg['host']}:{cfg.get('port',3306)}/"
        f"{cfg['database']}?charset=utf8mb4"
    )
    return create_engine(
        uri,
        pool_size=6,
        pool_recycle=3_600,
        pool_pre_ping=True,   # auto-revalidate sockets
        echo=DEBUG,           # ⇐ log SQL to console when debugging
    )


engine: Engine = _get_engine()

T = TypeVar("T")


def _with_retry(func: Callable[..., T], /, *args, **kwargs) -> T:
    """Run `func` and retry once on transient connection errors."""
    for attempt in (1, 2):
        try:
            return func(*args, **kwargs)
        except (OperationalError, InterfaceError) as err:
            if attempt == 2:
                raise
            if DEBUG:
                st.warning(f"DB retry due to: {err}")
            time.sleep(0.5)
            engine.dispose()  # drop pool → fresh sockets


# ── Base wrapper ────────────────────────────────────────────
class DatabaseManager:
    # ---------- READ ----------
    def fetch_data(self, sql: str, params: Sequence[Any] | None = None) -> pd.DataFrame:
        def _read():
            return pd.read_sql_query(text(sql), engine, params=params)

        try:
            return _with_retry(_read)
        except SQLAlchemyError as err:
            st.error(f"❌ DB read failed: {err}")
            return pd.DataFrame()

    # ---------- WRITE ----------
    def execute(self, sql: str, params: Sequence[Any] | None = None) -> None:
        def _write():
            with engine.begin() as conn:
                conn.execute(text(sql), params or {})
        _with_retry(_write)


# ╭────────────────────────────────────────────────────────────╮
# │  Shelf-specific helpers                                   │
# ╰────────────────────────────────────────────────────────────╯
class ShelfHandler(DatabaseManager):
    # 2.0  Debug sidebar panel
    def debug_panel(self) -> None:
        """Show recent rows and DSN when DEBUG is True."""
        if not DEBUG:
            return
        with st.sidebar.expander("🔎 DB Debug", expanded=False):
            st.caption("Latest 5 rows in **shelf**")
            st.dataframe(
                self.fetch_data(
                    "SELECT * FROM shelf ORDER BY lastupdated DESC LIMIT 5"
                )
            )
            st.caption("Latest 5 rows in **shelfentries**")
            st.dataframe(
                self.fetch_data(
                    "SELECT * FROM shelfentries ORDER BY entrydate DESC LIMIT 5"
                )
            )
            cfg = st.secrets["mysql"]
            st.caption("Current DSN")
            st.code(
                f"{cfg['user']}@{cfg['host']}:{cfg.get('port',3306)}/{cfg['database']}",
                language="bash",
            )

    # 2.1 current shelf items
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

    # 2.2 last locid helper
    def last_locid(self, itemid: int) -> str | None:
        df = self.fetch_data(
            """
            SELECT locid
            FROM   shelfentries
            WHERE  itemid = :itemid AND locid IS NOT NULL
            ORDER  BY entrydate DESC LIMIT 1
            """,
            {"itemid": itemid},
        )
        return None if df.empty else str(df.iloc[0, 0])

    # 2.3 upsert + log + inventory decrement
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
        def _tx():
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO shelf (itemid, expirationdate, quantity,
                                           cost_per_unit, locid)
                        VALUES (:itemid,:exp,:qty,:cpu,:loc) AS new
                        ON DUPLICATE KEY UPDATE
                            quantity      = shelf.quantity + new.quantity,
                            cost_per_unit = new.cost_per_unit,
                            locid         = new.locid,
                            lastupdated   = CURRENT_TIMESTAMP
                        """
                    ),
                    dict(
                        itemid=itemid,
                        exp=expirationdate,
                        qty=int(quantity),
                        cpu=float(cost_per_unit),
                        loc=locid,
                    ),
                )
                conn.execute(
                    text(
                        """
                        INSERT INTO shelfentries
                               (itemid, expirationdate, quantity,
                                createdby, locid)
                        VALUES (:itemid,:exp,:qty,:user,:loc)
                        """
                    ),
                    dict(
                        itemid=itemid,
                        exp=expirationdate,
                        qty=int(quantity),
                        user=created_by,
                        loc=locid,
                    ),
                )
                conn.execute(
                    text(
                        """
                        UPDATE inventory
                        SET quantity = quantity - :qty
                        WHERE itemid = :itemid
                          AND expirationdate = :exp
                          AND cost_per_unit  = :cpu
                        """
                    ),
                    dict(
                        qty=int(quantity),
                        itemid=itemid,
                        exp=expirationdate,
                        cpu=float(cost_per_unit),
                    ),
                )

        _with_retry(_tx)

    # 2.4 inventory lookup
    def get_inventory_by_barcode(self, barcode: str) -> pd.DataFrame:
        return self.fetch_data(
            """
            SELECT inv.itemid, i.itemnameenglish AS itemname,
                   inv.quantity, inv.expirationdate, inv.cost_per_unit
            FROM   inventory inv
            JOIN   item i ON inv.itemid = i.itemid
            WHERE  i.barcode = :bc AND inv.quantity > 0
            ORDER  BY inv.expirationdate
            """,
            {"bc": barcode},
        )

    # 2.5 shortage resolver
    def resolve_shortages(self, *, itemid: int, qty_need: int, user: str) -> int:
        remaining = qty_need

        def _tx() -> int:
            nonlocal remaining
            with engine.begin() as conn:
                rows = conn.execute(
                    text(
                        """
                        SELECT shortageid, shortage_qty
                        FROM   shelf_shortage
                        WHERE  itemid = :itemid AND resolved = FALSE
                        ORDER  BY logged_at FOR UPDATE
                        """
                    ),
                    {"itemid": itemid},
                ).mappings()
                for row in rows:
                    if remaining == 0:
                        break
                    take = min(remaining, int(row["shortage_qty"]))
                    conn.execute(
                        text(
                            """
                            UPDATE shelf_shortage
                            SET shortage_qty = shortage_qty - :take,
                                resolved      = (shortage_qty - :take = 0),
                                resolved_qty  = COALESCE(resolved_qty,0)+:take,
                                resolved_at   = CASE
                                                 WHEN shortage_qty - :take = 0
                                                 THEN CURRENT_TIMESTAMP END,
                                resolved_by   = :user
                            WHERE shortageid = :sid
                            """
                        ),
                        {"take": take, "user": user, "sid": row["shortageid"]},
                    )
                    remaining -= take
                conn.execute(text("DELETE FROM shelf_shortage WHERE shortage_qty = 0"))
            return remaining

        return _with_retry(_tx)

    # 2.6 quick low stock
    @st.cache_data(ttl=10)
    def get_low_shelf_stock(_self, threshold: int = 10) -> pd.DataFrame:
        return _self.fetch_data(
            """
            SELECT s.itemid, i.itemnameenglish AS itemname,
                   s.quantity, s.expirationdate
            FROM   shelf s
            JOIN   item i ON s.itemid = i.itemid
            WHERE  s.quantity <= :thr
            ORDER  BY s.quantity
            """,
            {"thr": threshold},
        )

    # 2.7 item master list
    @st.cache_data(ttl=30)
    def get_all_items(_self) -> pd.DataFrame:
        df = _self.fetch_data(
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

    # 2.7b update shelf settings
    def update_shelf_settings(self, itemid: int, thr: int, avg: int) -> None:
        self.execute(
            """
            UPDATE item
            SET shelfthreshold = :thr,
                shelfaverage   = :avg
            WHERE itemid      = :id
            """,
            {"thr": int(thr), "avg": int(avg), "id": int(itemid)},
        )

    # 2.8 quantity by item
    @st.cache_data(ttl=10)
    def get_shelf_quantity_by_item(_self) -> pd.DataFrame:
        df = _self.fetch_data(
            """
            SELECT i.itemid,
                   i.itemnameenglish AS itemname,
                   COALESCE(SUM(s.quantity),0) AS totalquantity,
                   i.shelfthreshold,
                   i.shelfaverage
            FROM   item i
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
