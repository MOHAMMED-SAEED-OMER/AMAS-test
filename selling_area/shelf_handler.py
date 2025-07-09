# selling_area/shelf_handler.py
"""
ShelfHandler – helper class for the Selling-Area module
=======================================================

A thin wrapper around **DatabaseManager** (which uses PyMySQL) that provides
shelf-specific database helpers for your Streamlit pages.

Functions included
------------------
list_shelves()              → all shelves with capacity & usage
add_shelf(name, capacity)   → create a new shelf
delete_shelf(id)            → safe delete (only when empty)
get_items_in_shelf(id)      → items & quantities on a shelf
search_items(term)          → fuzzy search across shelves
move_item(...)              → transfer quantity between shelves + audit log
low_stock_alerts(threshold) → items below a total-stock threshold
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from db_handler import DatabaseManager


class ShelfHandler(DatabaseManager):
    """Shelf-level data helpers built on top of DatabaseManager."""

    # ─────────────────────────────────────────────────────────────
    # Shelf CRUD
    # ─────────────────────────────────────────────────────────────
    def list_shelves(self) -> pd.DataFrame:
        """Return all shelves with capacity and current utilisation."""
        return self.fetch_data(
            """
            SELECT shelfid,
                   shelfname,
                   capacity,
                   (
                     SELECT COALESCE(SUM(quantity),0)
                     FROM   shelf_items si
                     WHERE  si.shelfid = s.shelfid
                   ) AS used_capacity
            FROM   shelf AS s
            ORDER  BY shelfname;
            """
        )

    def add_shelf(self, name: str, capacity: int | None = None) -> None:
        """Insert a new shelf row."""
        self.execute_command(
            "INSERT INTO shelf (shelfname, capacity) VALUES (%s, %s)",
            (name, capacity),
        )

    def delete_shelf(self, shelf_id: int) -> None:
        """
        Delete a shelf only if it is empty.
        Raises ValueError if items are still present.
        """
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
    def get_items_in_shelf(self, shelf_id: int) -> pd.DataFrame:
        """Return items and quantities stored on one shelf."""
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
        """Case-insensitive search across item names."""
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
        """
        Move `qty` of `item_id` from `from_shelf` to `to_shelf`
        and log the transfer.
        """
        if qty <= 0:
            raise ValueError("Quantity must be positive")

        # Decrease on source
        self.execute_command(
            """
            UPDATE shelf_items
            SET    quantity = quantity - %s
            WHERE  itemid   = %s
              AND  shelfid  = %s
            """,
            (qty, item_id, from_shelf),
        )

        # Increase on destination (insert row if new)
        self.execute_command(
            """
            INSERT INTO shelf_items (shelfid, itemid, quantity)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE quantity = quantity + VALUES(quantity)
            """,
            (to_shelf, item_id, qty),
        )

        # Audit trail
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
        """Return items whose total quantity is below `threshold`."""
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
