# item/item_handler.py  – prepared cursors + reliable last-insert id
import pandas as pd
import streamlit as st
from db_handler import DatabaseManager


class ItemHandler(DatabaseManager):
    """All item-related DB helpers (MySQL)."""

    # ───────────────────────────── Items ─────────────────────────────
    def get_items(self) -> pd.DataFrame:
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

    # ───────────────────── Suppliers (simple selects) ─────────────────────
    def get_suppliers(self) -> pd.DataFrame:
        return self.fetch_data(
            "SELECT supplierid, suppliername FROM `supplier` ORDER BY suppliername"
        )

    def get_item_suppliers(self, item_id: int) -> list[int]:
        df = self.fetch_data(
            "SELECT supplierid FROM `itemsupplier` WHERE itemid = %s", (item_id,)
        )
        return df["supplierid"].astype(int).tolist() if not df.empty else []

    # ────────────────────────── INSERT ──────────────────────────────
    def add_item(self, item_data: dict, supplier_ids: list[int]) -> int | None:
        """
        Insert a new item (prepared statement for safe BLOB handling),
        then link suppliers.  Returns new itemid or None.
        """
        cols = ", ".join(item_data.keys())
        ph = ", ".join(["%s"] * len(item_data))
        sql = (
            f"INSERT INTO `item` ({cols}, createdat, updatedat) "
            f"VALUES ({ph}, NOW(), NOW())"
        )

        self._ensure_live_conn()

        # 1️⃣  prepared INSERT so binary data isn't checked for UTF-8
        with self.conn.cursor(prepared=True) as cur:
            cur.execute(sql, list(item_data.values()))

        # 2️⃣  fetch the new AUTO_INCREMENT id reliably
        with self.conn.cursor() as cur2:  # regular cursor ok here
            cur2.execute("SELECT LAST_INSERT_ID()")
            item_id = cur2.fetchone()[0]

        self.conn.commit()

        if item_id:
            self.link_item_suppliers(item_id, supplier_ids)
            return int(item_id)
        return None

    # ──────────────────── supplier-link helpers ─────────────────────
    def link_item_suppliers(self, item_id: int, supplier_ids: list[int]) -> None:
        if not supplier_ids:
            return
        values = ", ".join(["(%s, %s)"] * len(supplier_ids))
        params = []
        for sid in supplier_ids:
            params.extend([item_id, sid])

        self.execute_command(
            f"INSERT IGNORE INTO `itemsupplier` (itemid, supplierid) VALUES {values}",
            tuple(params),
        )

    def update_item_suppliers(self, item_id: int, supplier_ids: list[int]) -> None:
        self.execute_command("DELETE FROM `itemsupplier` WHERE itemid = %s", (item_id,))
        self.link_item_suppliers(item_id, supplier_ids)

    # ────────────────────────── UPDATE ─────────────────────────────
    def update_item(self, item_id: int, updated_data: dict) -> None:
        if not updated_data:
            st.warning("⚠️ No changes made.")
            return
        set_clause = ", ".join(f"{k} = %s" for k in updated_data)
        sql = f"UPDATE `item` SET {set_clause}, updatedat = NOW() WHERE itemid = %s"
        params = list(updated_data.values()) + [item_id]

        self._ensure_live_conn()
        with self.conn.cursor(prepared=True) as cur:
            cur.execute(sql, params)
        self.conn.commit()

    # ────────────────────────── DELETE ─────────────────────────────
    def delete_item(self, itemid: int) -> None:
        conflicts = self.check_foreign_key_references(
            referenced_table="item", referenced_column="itemid", value=itemid
        )
        if conflicts:
            raise ValueError(
                f"Cannot delete item {itemid}: still referenced by {', '.join(conflicts)}"
            )
        self.execute_command("DELETE FROM `itemsupplier` WHERE itemid = %s", (itemid,))
        self.execute_command("DELETE FROM `item` WHERE itemid = %s", (itemid,))

    # ───────────── picture helpers (Add Pictures tab) ──────────────
    def get_items_without_pictures(self) -> pd.DataFrame:
        return self.fetch_data(
            """
            SELECT itemid, itemnameenglish
              FROM `item`
             WHERE itempicture IS NULL
                OR LENGTH(itempicture) = 0
             ORDER BY itemnameenglish
            """
        )

    def update_item_picture(self, item_id: int, picture_data: bytes) -> None:
        sql = """
            UPDATE `item`
               SET itempicture = %s,
                   updatedat   = NOW()
             WHERE itemid      = %s
        """
        self._ensure_live_conn()
        with self.conn.cursor(prepared=True) as cur:
            cur.execute(sql, (picture_data, item_id))
        self.conn.commit()

        # ───────────────────── Dropdown utilities ──────────────────────
    def get_dropdown_values(self, section: str) -> list[str]:
        """
        Return the list of dropdown values for a section, ordered alphabetically.
        (No internal caching here; the calling tab handles caching.)
        """
        df = self.fetch_data(
            "SELECT value FROM `dropdowns` WHERE section = %s ORDER BY value",
            (section,),
        )
        return df["value"].tolist() if not df.empty else []

    def add_dropdown_value(self, section: str, value: str) -> int | None:
        """
        Insert a dropdown value and return its id.

        • Omits the `id` column so MySQL auto-generates it.
        • Uses INSERT IGNORE to avoid duplicate errors.
        • If the value already exists, fetch and return the existing id.
        """
        self._ensure_live_conn()
        with self.conn.cursor(prepared=True) as cur:
            cur.execute(
                "INSERT IGNORE INTO `dropdowns` (section, value) VALUES (%s, %s)",
                (section, value),
            )
            self.conn.commit()

            if cur.rowcount:           # 1 → inserted
                return cur.lastrowid   # new id

            # rowcount 0 → duplicate skipped; fetch current id
            cur.execute(
                "SELECT id FROM `dropdowns` WHERE section = %s AND value = %s",
                (section, value),
            )
            row = cur.fetchone()
            return int(row[0]) if row else None

    def delete_dropdown_value(self, section: str, value: str) -> None:
        """Remove a dropdown entry (safe if it doesn’t exist)."""
        self.execute_command(
            "DELETE FROM `dropdowns` WHERE section = %s AND value = %s",
            (section, value),
        )
