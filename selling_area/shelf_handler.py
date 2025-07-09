"""
selling_area/shelf_handler.py
─────────────────────────────
Thin wrapper around the DB layer for shelf management tasks.

• Works with the existing DatabaseManager (`db_handler.py`).
• Resilient: pings / reconnects handled by DatabaseManager.
• Exposes **ShelfHandler** plus the modern and legacy helper methods
  expected by shelf.py, transfer.py, alerts.py, shelf_manage.py, etc.
"""

from __future__ import annotations

from typing import Any, Sequence, List, Dict

import pandas as pd

# Import your project-wide DB helper
from db_handler import DatabaseManager


__all__ = ["ShelfHandler"]  # makes “from … import ShelfHandler” safe


class ShelfHandler:
    """High-level helper focused on shelf-area queries & updates."""

    # --------------------------------------------------------------------- #
    # Construction                                                          #
    # --------------------------------------------------------------------- #
    def __init__(self, db: DatabaseManager | None = None) -> None:
        # Allow injection for unit-tests; otherwise use the singleton.
        self.db: DatabaseManager = db or DatabaseManager()

    # --------------------------------------------------------------------- #
    # READ QUERIES                                                          #
    # --------------------------------------------------------------------- #
    def get_all_items(self) -> pd.DataFrame:
        """Return item list with threshold / average columns (used by UI)."""
        df = self.db.fetch_data(
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
            # Convert nullable INT columns to pandas Int64 dtype
            df[["shelfthreshold", "shelfaverage"]] = df[
                ["shelfthreshold", "shelfaverage"]
            ].astype("Int64")
        return df

    # Legacy alias (transfer.py etc.) --------------------------------------
    fetch_all_items = get_all_items  # type: ignore[assignment]

    def get_shelf_grid(self) -> pd.DataFrame:
        """Detailed view of every shelf row (used by shelf.py)."""
        return self.db.fetch_data(
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

    # Legacy alias
    get_shelf_items = get_shelf_grid  # type: ignore[assignment]

    def low_stock(self, threshold: int = 10) -> pd.DataFrame:
        """Return rows whose quantity <= threshold (used by alerts)."""
        return self.db.fetch_data(
            """
            SELECT s.itemid,
                   i.itemnameenglish AS itemname,
                   s.quantity,
                   s.expirationdate
            FROM   shelf s
            JOIN   item  i ON s.itemid = i.itemid
            WHERE  s.quantity <= %s
            ORDER  BY s.quantity
            """,
            (threshold,),
        )

    # Legacy alias
    get_low_shelf_stock = low_stock  # type: ignore[assignment]

    # --------------------------------------------------------------------- #
    # WRITE / UPDATE OPERATIONS                                             #
    # --------------------------------------------------------------------- #
    def update_thresholds(self, itemid: int, thr: int, avg: int) -> None:
        """Canonical method to persist new threshold / average."""
        self.db.execute_command(
            """
            UPDATE item
            SET shelfthreshold = %s,
                shelfaverage   = %s
            WHERE itemid       = %s
            """,
            (int(thr), int(avg), int(itemid)),
        )

    # === UI & back-compat synonyms =======================================
    update_shelf_settings = update_thresholds           # shelf_manage.py
    set_shelf_settings    = update_thresholds           # possible old naming
    save_shelf_settings   = update_thresholds           # "

    # --------------------------------------------------------------------- #
    # Example mutation: add stock to shelf                                  #
    # --------------------------------------------------------------------- #
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
        """Upsert into shelf, add audit record, and deduct inventory."""
        self.db.execute_command(
            """
            INSERT INTO shelf (itemid, expirationdate, quantity,
                               cost_per_unit, locid)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                  quantity      = quantity + VALUES(quantity),
                  cost_per_unit = VALUES(cost_per_unit),
                  locid         = VALUES(locid),
                  lastupdated   = CURRENT_TIMESTAMP
            """,
            (itemid, expirationdate, int(quantity), float(cost_per_unit), locid),
        )
        self.db.execute_command(
            """
            INSERT INTO shelfentries
                   (itemid, quantity, expirationdate,
                    createdby, locid)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (itemid, int(quantity), expirationdate, created_by, locid),
        )
        self.db.execute_command(
            """
            UPDATE inventory
            SET quantity = quantity - %s
            WHERE itemid = %s
              AND expirationdate = %s
              AND cost_per_unit  = %s
            """,
            (int(quantity), itemid, expirationdate, float(cost_per_unit)),
        )
