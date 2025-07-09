"""
selling_area/shelf_handler.py
─────────────────────────────
• Pure-Python driver if available (PyMySQL) → no seg-faults.
• Falls back to mysql-connector automatically if PyMySQL missing.
• Resilient SQLAlchemy engine with pool_pre_ping + one-retry logic.
• Back-compat shims: get_shelf_items() *and* fetch_data() provided.
"""

from __future__ import annotations

import importlib
import time
from typing import Any, Sequence, Callable, List, TypeVar

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError, InterfaceError, SQLAlchemyError

# ── 0. Driver URI (prefer PyMySQL) ──────────────────────────
def _driver_uri() -> str:
    cfg = st.secrets["mysql"]
    if importlib.util.find_spec("pymysql") is not None:
        driver = "mysql+pymysql://"
    else:
        st.warning(
            "⚠️  PyMySQL not found; falling back to mysql-connector. "
            "Add `pymysql>=1.1` to requirements.txt for safer runtime."
        )
        driver = "mysql+mysqlconnector://"
    return (
        f"{driver}{cfg['user']}:{cfg['password']}@"
        f"{cfg['host']}:{cfg.get('port',3306)}/{cfg['database']}?charset=utf8mb4"
    )

# ── 1. Engine and retry helper ──────────────────────────────
@st.cache_resource(show_spinner=False)
def _get_engine() -> Engine:
    return create_engine(
        _driver_uri(),
        pool_size=6,
        pool_pre_ping=True,
        pool_recycle=3_600,
        future=True,
    )


engine: Engine = _get_engine()
T = TypeVar("T")


def _retry(fn: Callable[..., T], /, *a, **kw) -> T:
    for attempt in (1, 2):
        try:
            return fn(*a, **kw)
        except (OperationalError, InterfaceError):
            if attempt == 2:
                raise
            engine.dispose()
            time.sleep(0.5)

# ── 2. Thin DB wrapper ──────────────────────────────────────
class DB:
    # preferred modern name
    def df(self, sql: str, params: Sequence[Any] | None = None) -> pd.DataFrame:
        def _read():
            return pd.read_sql_query(text(sql), engine, params=params)
        try:
            return _retry(_read)
        except SQLAlchemyError as e:
            st.error(f"❌ DB read failed: {e}")
            return pd.DataFrame()

    # legacy alias expected by transfer.py and others
    def fetch_data(self, sql: str, params: Sequence[Any] | None = None) -> pd.DataFrame:  # noqa: N802
        return self.df(sql, params)

    # write
    def exec(self, sql: str, params: Sequence[Any] | None = None) -> None:
        def _write():
            with engine.begin() as c:
                c.execute(text(sql), params or {})
        _retry(_write)

# ── 3. Shelf helper ─────────────────────────────────────────
class ShelfHandler(DB):
    # --- READ shelf grid ------------------------------------
    @st.cache_data(ttl=10)
    def shelf_grid(_s) -> pd.DataFrame:
        return _s.df(
            """
            SELECT s.shelfid, s.itemid, i.itemnameenglish AS itemname,
                   s.quantity, s.expirationdate, s.cost_per_unit,
                   s.locid, s.lastupdated
            FROM shelf s
            JOIN item i ON s.itemid = i.itemid
            ORDER BY i.itemnameenglish, s.expirationdate
            """
        )

    # alias for legacy UI
    def get_shelf_items(self) -> pd.DataFrame:  # noqa: N802
        return self.shelf_grid()

    # --- READ last locid ------------------------------------
    def last_locid(self, itemid: int) -> str | None:
        df = self.df(
            """
            SELECT locid
            FROM shelfentries
            WHERE itemid = :itemid AND locid IS NOT NULL
            ORDER BY entrydate DESC LIMIT 1
            """,
            {"itemid": itemid},
        )
        return None if df.empty else str(df.loc[0, "locid"])

    # --- WRITE add / move -----------------------------------
    def add_to_shelf(
        self,
        *,
        itemid: int,
        expirationdate,
        quantity: int,
        cost_per_unit: float,
        locid: str,
        created_by: str,
    ) -> None:
        def _tx():
            with engine.begin() as c:
                # shelf upsert
                c.execute(
                    text(
                        """
                        INSERT INTO shelf (itemid, expirationdate, quantity,
                                           cost_per_unit, locid)
                        VALUES (:item,:exp,:qty,:cpu,:loc)
                        ON DUPLICATE KEY UPDATE
                          quantity      = quantity + VALUES(quantity),
                          cost_per_unit = VALUES(cost_per_unit),
                          locid         = VALUES(locid),
                          lastupdated   = CURRENT_TIMESTAMP
                        """
                    ),
                    dict(item=itemid, exp=expirationdate, qty=int(quantity),
                         cpu=float(cost_per_unit), loc=locid),
                )

                # shelfentries row (entryid & entrydate handled by DB defaults)
                c.execute(
                    text(
                        """
                        INSERT INTO shelfentries
                               (itemid, quantity, expirationdate,
                                createdby, locid)
                        VALUES (:item,:qty,:exp,:user,:loc)
                        """
                    ),
                    dict(item=itemid, qty=int(quantity), exp=expirationdate,
                         user=created_by, loc=locid),
                )

                # inventory decrement
                c.execute(
                    text(
                        """
                        UPDATE inventory
                        SET quantity = quantity - :qty
                        WHERE itemid = :item AND expirationdate = :exp
                          AND cost_per_unit = :cpu
                        """
                    ),
                    dict(qty=int(quantity), item=itemid, exp=expirationdate,
                         cpu=float(cost_per_unit)),
                )
        _retry(_tx)

    # --- READ inventory by barcode --------------------------
    def inv_by_barcode(self, barcode: str) -> pd.DataFrame:
        return self.df(
            """
            SELECT inv.itemid, i.itemnameenglish AS itemname,
                   inv.quantity, inv.expirationdate, inv.cost_per_unit
            FROM inventory inv
            JOIN item i ON inv.itemid = i.itemid
            WHERE i.barcode = :bc AND inv.quantity > 0
            ORDER BY inv.expirationdate
            """,
            {"bc": barcode},
        )

    # --- shortage resolution --------------------------------
    def resolve_shortages(self, itemid: int, qty_need: int, user: str) -> int:
        remaining = qty_need

        def _tx() -> int:
            nonlocal remaining
            with engine.begin() as c:
                rows = c.execute(
                    text(
                        """
                        SELECT shortageid, shortage_qty
                        FROM shelf_shortage
                        WHERE itemid = :item AND resolved = FALSE
                        ORDER BY logged_at FOR UPDATE
                        """
                    ),
                    {"item": itemid},
                ).mappings()

                for r in rows:
                    if remaining == 0:
                        break
                    take = min(remaining, int(r["shortage_qty"]))
                    c.execute(
                        text(
                            """
                            UPDATE shelf_shortage
                            SET shortage_qty = shortage_qty - :take,
                                resolved      = (shortage_qty - :take = 0),
                                resolved_qty  = COALESCE(resolved_qty,0)+:take,
                                resolved_at   = IF(shortage_qty - :take = 0,
                                                   CURRENT_TIMESTAMP, resolved_at),
                                resolved_by   = :u
                            WHERE shortageid = :sid
                            """
                        ),
                        {"take": take, "u": user, "sid": r["shortageid"]},
                    )
                    remaining -= take

                c.execute(text("DELETE FROM shelf_shortage WHERE shortage_qty = 0"))
            return remaining

        return _retry(_tx)

    # --- READ low stock -------------------------------------
    @st.cache_data(ttl=10)
    def low_stock(_s, threshold: int = 10) -> pd.DataFrame:
        return _s.df(
            """
            SELECT s.itemid, i.itemnameenglish AS itemname,
                   s.quantity, s.expirationdate
            FROM shelf s
            JOIN item i ON s.itemid = i.itemid
            WHERE s.quantity <= :thr
            ORDER BY s.quantity
            """,
            {"thr": threshold},
        )

    # --- READ all items -------------------------------------
    @st.cache_data(ttl=30)
    def all_items(_s) -> pd.DataFrame:
        df = _s.df(
            """
            SELECT itemid, itemnameenglish AS itemname,
                   shelfthreshold, shelfaverage
            FROM item ORDER BY itemnameenglish
            """
        )
        if not df.empty:
            df["shelfthreshold"] = df["shelfthreshold"].astype("Int64")
            df["shelfaverage"] = df["shelfaverage"].astype("Int64")
        return df

    # --- update thresholds ----------------------------------
    def update_thresholds(self, itemid: int, thr: int, avg: int) -> None:
        self.exec(
            """
            UPDATE item
            SET shelfthreshold = :thr, shelfaverage = :avg
            WHERE itemid = :id
            """,
            {"thr": int(thr), "avg": int(avg), "id": int(itemid)},
        )

    # --- READ quantity summary ------------------------------
    @st.cache_data(ttl=10)
    def qty_by_item(_s) -> pd.DataFrame:
        df = _s.df(
            """
            SELECT i.itemid, i.itemnameenglish AS itemname,
                   COALESCE(SUM(s.quantity),0) AS totalquantity,
                   i.shelfthreshold, i.shelfaverage
            FROM item i
            LEFT JOIN shelf s ON i.itemid = s.itemid
            GROUP BY i.itemid, i.itemnameenglish,
                     i.shelfthreshold, i.shelfaverage
            ORDER BY i.itemnameenglish
            """
        )
        if not df.empty:
            df["totalquantity"] = df["totalquantity"].astype(int)
            df["shelfthreshold"] = df["shelfthreshold"].astype("Int64")
            df["shelfaverage"] = df["shelfaverage"].astype("Int64")
        return df
