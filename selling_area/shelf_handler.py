# selling_area/shelf_handler.py
"""
ShelfHandler – Selling-Area database helpers (MySQL / PyMySQL edition)
======================================================================

Depends on db_handler.DatabaseManager, which uses a cached PyMySQL
connection under Streamlit’s session cache.

Public methods
--------------
• list_shelves()              → shelves with capacity & used_capacity
• add_shelf(name, capacity)   → create shelf
• delete_shelf(id)            → safe delete when empty
• get_shelf_items()           → all items on all shelves   ← NEW
• get_items_in_shelf(id)      → items on one shelf
• search_items(term)          → fuzzy search
• move_item(...)              → transfer + audit trail
• low_stock_alerts(threshold) → items below threshold
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from db_handler import DatabaseManager


class ShelfHandler(DatabaseManager):
    """Shelf-specific helpers built on top of DatabaseManager."""

    # ─────────────────────────────────────────────────────────────
    # Shelf CRUD
    # ─────────────────────────────────────────────────────────────
    def list_shelves(self) -> pd.DataFrame:
        return self.fetch_data(
            """
            SELECT s.shelfid,
                   s.shelfname,
                   s.capacity,
                   COALESCE(SUM(si.quantity), 0) AS used_capacity
            FROM   shelf s
            LEFT   JOIN shelf_items si USING (shelfid)
            GROUP  BY s.shelfid, s.shelfname, s.capacity
            ORDER  BY s.shelfname;
            """
        )

    def add_shelf(self, name: str, capacity: int | None = None) -> None:
        self.execute_command(
            "INSERT INTO shelf (shelfname, capacity) VALUES (%s, %s)",
            (name, capacity),
        )

    def delete_shelf(self, shelf_id: int) -> None:
        has_items = self.fetch_data(
            "SELECT EXISTS(SELECT 1 FROM shelf_items WHERE shelfid = %s)",
            (shelf_id,),
        ).iat[0, 0]
        if has_items:
            raise ValueError("Cannot delete shelf: items still assigned.")
        self.execute_command("DELETE FROM shelf WHERE shelfid = %s", (shelf_id,))

    # ─────────────────────────────────────────────────────────────
    # Item queries
    # ─────────────────────────────────────────────────────────────
    def get_shelf_items(self) -> pd.DataFrame:
        """
        Return every item on every shelf.

        Columns: shelfid, shelfname, itemid, itemname, quantity, uom
        """
        return self.fetch_data(
            """
            SELECT s.shelfid,
                   s.shelfname,
                   i.itemid,
                   i.itemname,
                   si.quantity,
                   i.uom
            FROM   shelf_items si
            JOIN   shelf       s  USING (shelfid)
            JOIN   item        i  USING (itemid)
            ORDER  BY s.shelfname, i.itemname;
            """
        )

    def get_items_in_shelf(self, shelf_id: int) -> pd.DataFrame:
        return self.fetch_data(
            """
            SELECT i.itemid,
                   i.itemname,
                   si.quantity,
                   i.uom
            FROM   shelf_items si
            JOIN   item        i USING (itemid)
            WHERE  si.shelfid = %s
            ORDER  BY i.itemname;
            """,
            (shelf_id,),
        )

    def search_items(self, term: str) -> pd.DataFrame:
        like = f"%{term}%"
        return self.fetch_data(
            """
            SELECT i.itemid,
                   i.itemname,
                   s.shelfname,
                   si.quantity
            FROM   item i
            JOIN   shelf_items si USING (itemid)
            JOIN   shelf       s  USING (shelfid)
            WHERE  i.itemname LIKE %s
            ORDER  BY i.itemname;
            """,
            (like,),
        )

    # ─────────────────────────────────────────────────────────────
    # Transfers
    # ─────────────────────────────────────────────────────────────
    def move_item(
        self,
        item_id: int,
        from_shelf: int,
        to_shelf: int,
        qty: int,
        user_email: str | None = None,
    ) -> None:
        if qty <= 0:
            raise ValueError("Quantity must be positive")

        # Decrease source
        self.execute_command(
            """
            UPDATE shelf_items
            SET    quantity = quantity - %s
            WHERE  itemid   = %s
              AND  shelfid  = %s
            """,
            (qty, item_id, from_shelf),
        )

        # Increase / insert destination
        self.execute_command(
            """
            INSERT INTO shelf_items (shelfid, itemid, quantity)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
                  quantity = quantity + VALUES(quantity)
            """,
            (to_shelf, item_id, qty),
        )

        # Audit log
        self.execute_command(
            """
            INSERT INTO shelf_transfers
            (itemid, from_shelf, to_shelf, quantity, moved_by)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (item_id, from_shelf, to_shelf, qty, user_email),
        )

    # ─────────────────────────────────────────────────────────────
    # Alerts
    # ─────────────────────────────────────────────────────────────
    def low_stock_alerts(self, threshold: int = 5) -> pd.DataFrame:
        return self.fetch_data(
            """
            SELECT i.itemid,
                   i.itemname,
                   SUM(si.quantity) AS total_qty
            FROM   shelf_items si
            JOIN   item        i USING (itemid)
            GROUP  BY i.itemid, i.itemname
            HAVING SUM(si.quantity) < %s
            ORDER  BY total_qty;
            """,
            (threshold,),
        )
