import streamlit as st
import pandas as pd
from db_handler import DatabaseManager

class ItemHandler(DatabaseManager):
    """Handles all item-related database interactions separately."""

    # ✅ Item methods
    def get_items(self):
        """
        Fetch item data and ensure a valid DataFrame is returned even if no items exist.
        """
        query = "SELECT * FROM item"
        df = self.fetch_data(query)

        if df.empty:
            # ✅ Return an empty DataFrame with correct columns to prevent errors
            return pd.DataFrame(columns=[
                "itemid", "itemnameenglish", "itemnamekurdish", "classcat", "departmentcat",
                "sectioncat", "familycat", "subfamilycat", "shelflife", "threshold",
                "averagerequired", "origincountry", "manufacturer", "brand",
                "barcode", "packetbarcode", "cartonbarcode", "unittype", "packaging", "itempicture", "createdat", "updatedat"
            ])
        
        return df

    def get_suppliers(self):
        """Fetches the list of suppliers."""
        query = "SELECT SupplierID, SupplierName FROM Supplier"
        return self.fetch_data(query)

    def get_item_suppliers(self, item_id):
        """Fetches suppliers linked to a specific item."""
        query = """
        SELECT s.SupplierName FROM ItemSupplier isup
        JOIN Supplier s ON isup.SupplierID = s.SupplierID
        WHERE isup.ItemID = %s
        """
        df = self.fetch_data(query, (item_id,))
        return df["suppliername"].tolist() if not df.empty else []

    def add_item(self, item_data, supplier_ids):
        """Adds a new item and links it to suppliers."""
        columns = ", ".join(item_data.keys())
        placeholders = ", ".join(["%s"] * len(item_data))
        query = f"""
        INSERT INTO item ({columns}, createdat, updatedat)
        VALUES ({placeholders}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING itemid
        """
        item_id = self.execute_command_returning(query, list(item_data.values()))

        if item_id:
            self.link_item_suppliers(item_id[0], supplier_ids)
            return item_id[0]
        return None

    def link_item_suppliers(self, item_id, supplier_ids):
        """Links an item with selected suppliers."""
        if not supplier_ids:
            return
        values = ", ".join(["(%s, %s)"] * len(supplier_ids))
        params = []
        for supplier_id in supplier_ids:
            params.extend([item_id, supplier_id])
        query = f"""
        INSERT INTO itemsupplier (itemid, supplierid) 
        VALUES {values}
        ON CONFLICT DO NOTHING
        """
        self.execute_command(query, params)

    def update_item(self, item_id, updated_data):
        """Updates item details."""
        if not updated_data:
            st.warning("⚠️ No changes made.")
            return
        set_clause = ", ".join(f"{col} = %s" for col in updated_data.keys())
        query = f"""
        UPDATE item
        SET {set_clause}, updatedat = CURRENT_TIMESTAMP
        WHERE itemid = %s
        """
        params = list(updated_data.values()) + [item_id]
        self.execute_command(query, params)

    def update_item_suppliers(self, item_id, supplier_ids):
        """Updates suppliers linked to an item."""
        delete_query = "DELETE FROM ItemSupplier WHERE ItemID = %s"
        self.execute_command(delete_query, (item_id,))
        for supplier_id in supplier_ids:
            insert_query = "INSERT INTO ItemSupplier (ItemID, SupplierID) VALUES (%s, %s)"
            self.execute_command(insert_query, (item_id, supplier_id))

    # ✅ Dropdown methods
    def get_dropdown_values(self, section):
        """Fetches values from dropdown categories."""
        query = "SELECT value FROM Dropdowns WHERE section = %s"
        df = self.fetch_data(query, (section,))
        return df["value"].tolist() if not df.empty else []

    def add_dropdown_value(self, section, value):
        """Adds a new value to dropdown categories."""
        query = """
        INSERT INTO Dropdowns (section, value)
        VALUES (%s, %s)
        ON CONFLICT (section, value) DO NOTHING
        """
        self.execute_command(query, (section, value))

    def delete_dropdown_value(self, section, value):
        """Deletes a value from dropdown categories."""
        query = "DELETE FROM Dropdowns WHERE section = %s AND value = %s"
        self.execute_command(query, (section, value))

    # ✅ Methods for "Add Pictures" Tab
    def get_items_without_pictures(self):
        """Fetch items without pictures."""
        query = """
        SELECT ItemID, ItemNameEnglish
        FROM Item
        WHERE ItemPicture IS NULL OR length(ItemPicture) = 0
        """
        return self.fetch_data(query)

    def update_item_picture(self, item_id, picture_data):
        """Update item picture in database."""
        query = """
        UPDATE Item
        SET ItemPicture = %s, UpdatedAt = CURRENT_TIMESTAMP
        WHERE ItemID = %s
        """
        self.execute_command(query, (picture_data, item_id))

    def delete_item(self, itemid: int):
        """
        Delete an item only if it is not referenced anywhere else.
        Raises ValueError listing blocking tables if references exist.
        """
        conflicts = self.check_foreign_key_references(
            referenced_table="item",
            referenced_column="itemid",
            value=itemid,
        )

        if conflicts:
            tables = ", ".join(conflicts)
            raise ValueError(
                f"Cannot delete item {itemid}: the item is still referenced by "
                f"the following table(s): {tables}"
            )

        # remove supplier links first (optional but tidy)
        self.execute_command("DELETE FROM itemsupplier WHERE itemid = %s", (itemid,))

        # finally remove the item record itself
        self.execute_command("DELETE FROM item WHERE itemid = %s", (itemid,))
