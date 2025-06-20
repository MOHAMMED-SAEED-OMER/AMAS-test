import streamlit as st
import pandas as pd
from db_handler import DatabaseManager


class BarcodeShelfHandler(DatabaseManager):
    """Handles barcode‑based transfers from Inventory → Shelf (cost aware)."""

    # ───────────────────────── shelf insert/update ───────────────────
    def add_to_shelf(self,
                     itemid,
                     expirationdate,
                     quantity,
                     created_by,
                     cost_per_unit):
        """
        Upsert into Shelf WHERE (item, expiry, cost) all match.
        """
        check_query = """
        SELECT shelfid
        FROM   Shelf
        WHERE  itemid = %s
          AND  expirationdate = %s
          AND  cost_per_unit  = %s;
        """
        existing = self.fetch_data(check_query,
                                   (itemid, expirationdate, cost_per_unit))

        if not existing.empty:
            shelfid = int(existing.iloc[0]["shelfid"])
            self.execute_command(
                """
                UPDATE Shelf
                SET    quantity    = quantity + %s,
                       lastupdated = CURRENT_TIMESTAMP
                WHERE  shelfid = %s;
                """,
                (quantity, shelfid),
            )
        else:
            self.execute_command(
                """
                INSERT INTO Shelf
                      (itemid, expirationdate, quantity, cost_per_unit)
                VALUES (%s, %s, %s, %s);
                """,
                (itemid, expirationdate, quantity, cost_per_unit),
            )

        # Log movement (ShelfEntries has no cost column)
        self.execute_command(
            """
            INSERT INTO ShelfEntries
                  (itemid, expirationdate, quantity, createdby)
            VALUES (%s, %s, %s, %s);
            """,
            (itemid, expirationdate, quantity, created_by),
        )

    # ───────────────────── transfer core action ──────────────────────
    def transfer_from_inventory(self,
                                itemid,
                                expirationdate,
                                quantity,
                                cost_per_unit,
                                created_by):
        """
        Move qty from Inventory → Shelf, using the exact cost layer selected.
        """
        # 1. Decrement that specific cost layer in inventory
        self.execute_command(
            """
            UPDATE Inventory
            SET    quantity = quantity - %s
            WHERE  itemid         = %s
              AND  expirationdate = %s
              AND  cost_per_unit  = %s
              AND  quantity >= %s;
            """,
            (quantity, itemid, expirationdate, cost_per_unit, quantity),
        )

        # 2. Add to shelf (will merge only if same cost)
        self.add_to_shelf(
            itemid,
            expirationdate,
            quantity,
            created_by,
            cost_per_unit,
        )

    # ───────────────────── inventory queries ─────────────────────────
    def get_inventory_by_barcode(self, barcode):
        query = """
        SELECT inv.itemid,  i.itemnameenglish AS itemname,
               inv.quantity, inv.expirationdate,
               inv.storagelocation, inv.cost_per_unit
        FROM   Inventory inv
        JOIN   Item      i ON inv.itemid = i.itemid
        WHERE  i.barcode = %s AND inv.quantity > 0
        ORDER  BY inv.expirationdate, inv.cost_per_unit;
        """
        return self.fetch_data(query, (barcode,))


# ─────────────────────────── UI Layer ───────────────────────────────
def scan_transfer_tab(handler: BarcodeShelfHandler):
    st.subheader("📷 Scan Items to Transfer")
    st.markdown("Use barcode scanner or enter barcode manually:")

    barcode = st.text_input("📦 Scan Barcode")

    if not barcode:
        return

    inventory_data = handler.get_inventory_by_barcode(barcode)
    if inventory_data.empty:
        st.error("❌ No matching inventory item found for this barcode."); return

    st.success("✅ Item(s) found:")
    for idx, row in inventory_data.iterrows():
        location = row.get("storagelocation", "N/A")
        st.write(
            f"**{row['itemname']}** | Exp: {row['expirationdate']} "
            f"| Cost: {row['cost_per_unit']:.2f} "
            f"| Loc: {location} | Qty: {row['quantity']}"
        )

        with st.form(key=f"transfer_form_{idx}"):
            qty = st.number_input(
                f"Quantity to transfer (max {row['quantity']})",
                min_value=1,
                max_value=int(row["quantity"]),
                step=1,
                key=f"qty_{idx}",
            )

            if st.form_submit_button("📤 Transfer"):
                handler.transfer_from_inventory(
                    itemid=row["itemid"],
                    expirationdate=row["expirationdate"],
                    quantity=qty,
                    cost_per_unit=row["cost_per_unit"],   # pass exact cost
                    created_by=st.session_state.get("user_email", "Unknown"),
                )
                st.success("✅ Item transferred to shelf.")
                st.rerun()


# Manual test
if __name__ == "__main__":
    scan_transfer_tab(BarcodeShelfHandler())
