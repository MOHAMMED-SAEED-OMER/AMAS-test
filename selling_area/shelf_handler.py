"""
selling_area/shelf_handler.py
─────────────────────────────
High-level helper focused on shelf-area queries & updates.

Key points
──────────
• Wraps the project-wide DatabaseManager (db_handler.py) so we reuse the
  same resilient connection pool and retry logic.
• Exposes **ShelfHandler** plus *all* legacy method names older modules
  expect (`fetch_data`, `get_shelf_items`, `update_shelf_settings`, …).
"""

from __future__ import annotations

from typing import Any, Sequence, List

import pandas as pd

from db_handler import DatabaseManager

__all__ = ["ShelfHandler"]


class ShelfHandler:
    # ------------------------------------------------------------------ #
    # Initialise                                                          #
    # ------------------------------------------------------------------ #
    def __init__(self, db: DatabaseManager | None = None) -> None:
        # Allow dependency injection for tests; fallback to singleton
        self.db: DatabaseManager = db or DatabaseManager()

    # ------------------------------------------------------------------ #
    # Generic DB pass-throughs (needed by transfer.py, etc.)              #
    # ------------------------------------------------------------------ #
    def fetch_data(
        self, query: str, params: Sequence[Any] | None = None
    ) -> pd.DataFrame:
        """Direct passthrough to DatabaseManager.fetch_data()."""
        return self.db.fetch_data(query, params)

    def execute_command(
        self, query: str, params: Sequence[Any] | None = None
    ) -> None:
        """Passthrough to DatabaseManager.execute_command()."""
        self.db.execute_command(query, params)

    # ------------------------------------------------------------------ #
    # Item lists & shelf overviews                                        #
    # ------------------------------------------------------------------ #
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
            df[["shelfthreshold", "shelfaverage"]] = df[
                ["shelfthreshold", "shelfaverage"]
            ].astype("Int64")
        return df

    # legacy alias
    fetch_all_items = get_all_items  # type: ignore[assignment]

    def get_shelf_grid(self) -> pd.DataFrame:
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
            JOIN   item i ON s.itemid = i.itemid
            ORDER  BY i.itemnameenglish, s.expirationdate
            """
        )

    # legacy alias
    get_shelf_items = get_shelf_grid  # type: ignore[assignment]

    def low_stock(self, threshold: int = 10) -> pd.DataFrame:
        return self.fetch_data(
            """
            SELECT s.itemid,
                   i.itemnameenglish AS itemname,
                   s.quantity,
                   s.expirationdate
            FROM   shelf s
            JOIN   item i ON s.itemid = i.itemid
            WHERE  s.quantity <= %s
            ORDER  BY s.quantity
            """,
            (threshold,),
        )

    # legacy alias
    get_low_shelf_stock = low_stock  # type: ignore[assignment]

    # ------------------------------------------------------------------ #
    # Threshold helpers                                                  #
    # ------------------------------------------------------------------ #
    def update_thresholds(self, itemid: int, thr: int, avg: int) -> None:
        self.execute_command(
            """
            UPDATE item
            SET shelfthreshold = %s,
                shelfaverage   = %s
            WHERE itemid       = %s
            """,
            (int(thr), int(avg), int(itemid)),
        )

    # UI & back-compat synonyms
    update_shelf_settings = update_thresholds           # shelf_manage.py
    set_shelf_settings    = update_thresholds
    save_shelf_settings   = update_thresholds

    # ------------------------------------------------------------------ #
    # Example mutation: add stock to shelf                               #
    # ------------------------------------------------------------------ #
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
        self.execute_command(
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
        self.execute_command(
            """
            INSERT INTO shelfentries
                   (itemid, quantity, expirationdate,
                    createdby, locid)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (itemid, int(quantity), expirationdate, created_by, locid),
        )
        self.execute_command(
            """
            UPDATE inventory
            SET quantity = quantity - %s
            WHERE itemid = %s
              AND expirationdate = %s
              AND cost_per_unit  = %s
            """,
            (int(quantity), itemid, expirationdate, float(cost_per_unit)),
        )
