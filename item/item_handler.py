# item/item_handler.py  – MySQL backend
import math
import pandas as pd
import streamlit as st

from db_handler import DatabaseManager


class ItemHandler(DatabaseManager):
    """
    All item-related DB helpers
    (rewritten for MySQL, no RETURNING / ON CONFLICT).
    """

    # ───────────────────────────── Items ─────────────────────────────
    def get_items(self) -> pd.DataFrame:
        """Return every row from `item` (empty DF with columns if none)."""
        df = self.fetch_data("SELECT * FROM `item`")
        if df.empty:
            return pd.DataFrame(
                columns=[
                    "itemid",
                    "itemnameenglish",
                    "itemnamekurdish",
                    "classcat",
                    "departmentcat",
                    "sectioncat",
                    "familycat",
                    "subfamilycat",
                    "shelflife",
                    "threshold",
                    "averagerequired",
                    "origincountry",
                    "manufacturer",
                    "brand",
                    "barcode",
                    "packetbarcode",
                    "cartonbarcode",
                    "unittype",
                    "packaging",
                    "itempicture",
                    "createdat",
                    "updatedat",
                ]
            )
        return df

    # ───────────────────────── Suppliers ─────────────────────────────
    def get_suppliers(self) -> pd.DataFrame:
        return self.fetch_data(
            "SELECT supplierid, suppliername FROM `supplier` ORDER BY suppliername"
        )

    def get_item_suppliers(self, item_id: int) -> list[int]:
        """
        IDs of suppliers linked to a given item.
        (Fixed: now returns IDs, not names.)
        """
        q = "SELECT supplierid FROM `itemsupplier` WHERE itemid = %s"
        df = self.fetch_data(q, (item_id,))
        return df["supplierid"].astype(int).tolist() if not df.empty else []

    # ────────────────────────── INSERT ──────────────────────────────
    def add_item(self, item_data: dict, supplier_ids: list[int]) -> int | None:
        """
        Create a new item and link it to supplier IDs.
        Returns the new itemid.
        """
        cols  = ", ".join(item_data.keys())
        ph    = ", ".join(["%s"] * len(item_data))
        sql   = (
            f"INSERT INTO `item` ({cols}, createdat, updatedat) "
            f"VALUES ({ph}, NOW(), NOW())"
        )

        # Insert, fetch AUTO_INCREMENT via lastrowid
        self._ensure_live_conn()
        with self.conn.cursor() as cur:
            cur.execute(sql, list(item_data.values()))
            item_id = cur.lastrowid
        self.conn.commit()

        if item_id:
            self.link_item_suppliers(item_id, supplier_ids)
            return int(item_id)
        return None

    # ──────────────────── supplier-link helpers ─────────────────────
    def link_item_suppliers(self, item_id: int, supplier_ids: list[int]) -> None:
        """
        Insert into itemsupplier, ignore duplicates.
        """
        if not supplier_ids:
            return

        values = ", ".join(["(%s, %s)"] * len(supplier_ids))
        params = []
        for sid in supplier_ids:
            params.extend([item_id, sid])

        # INSERT IGNORE skips rows that would violate the PK
        sql = f"INSERT IGNORE INTO `itemsupplier` (itemid, supplierid) VALUES {values}"
        self.execute_command(sql, tuple(params))

    def update_item_suppliers(self, item_id: int, supplier_ids: list[int]) -> None:
        """
        Replace supplier links for an item.
        """
        self.execute_command("DELETE FROM `itemsupplier` WHERE itemid = %s", (item_id,))
        self.link_item_suppliers(item_id, supplier_ids)

    # ────────────────────────── UPDATE ─────────────────────────────
    def update_item(self, item_id: int, updated_data: dict) -> None:
        """
        Patch columns on an item row.
        """
        if not updated_data:
            st.warning("⚠️ No changes made.")
            return

        set_clause = ", ".join(f"{k} = %s" for k in updated_data)
        sql = (
            f"UPDATE `item` SET {set_clause}, updatedat = NOW() WHERE itemid = %s"
        )
        params = list(updated_data.values()) + [item_id]
        self.execute_command(sql, tuple(params))

    # ────────────────────────── DELETE ─────────────────────────────
    def delete_item(self, itemid: int) -> None:
        """
        Delete an item after verifying no FK references.
        """
        conflicts = self.check_foreign_key_references(
            referenced_table="item", referenced_column="itemid", value=itemid
        )
        if conflicts:
            raise ValueError(
                f"Cannot delete item {itemid}: still referenced by {', '.join(conflicts)}"
            )

        self.execute_command("DELETE FROM `itemsupplier` WHERE itemid = %s", (itemid,))
        self.execute_command("DELETE FROM `item` WHERE itemid = %s", (itemid,))

    # ───────────────────── Dropdown utilities ──────────────────────
    def get_dropdown_values(self, section: str) -> list[str]:
        df = self.fetch_data(
            "SELECT value FROM `dropdowns` WHERE section = %s ORDER BY value", (section,)
        )
        return df["value"].tolist() if not df.empty else []

    def add_dropdown_value(self, section: str, value: str) -> None:
        # INSERT IGNORE avoids duplicate key errors when (section,value) is UNIQUE
        self.execute_command(
            "INSERT IGNORE INTO `dropdowns` (section, value) VALUES (%s, %s)",
            (section, value),
        )

    def delete_dropdown_value(self, section: str, value: str) -> None:
        self.execute_command(
            "DELETE FROM `dropdowns` WHERE section = %s AND value = %s",
            (section, value),
        )

    # ───────────── picture helpers (Add Pictures tab) ──────────────
    def get_items_without_pictures(self) -> pd.DataFrame:
        """
        Items whose ItemPicture is NULL or empty (MySQL LENGTH)
        """
        q = """
            SELECT itemid, itemnameenglish
            FROM   `item`
            WHERE  itempicture IS NULL OR LENGTH(itempicture) = 0
            ORDER  BY itemnameenglish
        """
        return self.fetch_data(q)

    def update_item_picture(self, item_id: int, picture_data: bytes) -> None:
        self.execute_command(
            """
            UPDATE `item`
               SET itempicture = %s,
                   updatedat   = NOW()
             WHERE itemid      = %s
            """,
            (picture_data, item_id),
        )
