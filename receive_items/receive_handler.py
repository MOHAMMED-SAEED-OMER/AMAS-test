from db_handler import DatabaseManager
from psycopg2.extras import execute_values


class ReceiveHandler(DatabaseManager):
    """Handles database operations for receiving items, costs, and locations."""

    # ───────────────────────── POs to receive ─────────────────────────
    def get_received_pos(self):
        query = """
        SELECT po.poid,
               po.expecteddelivery,
               s.suppliername
        FROM   purchaseorders po
        JOIN   supplier s ON po.supplierid = s.supplierid
        WHERE  po.status = 'Received'
        """
        return self.fetch_data(query)

    def get_po_items(self, poid):
        query = """
        SELECT poi.itemid,
               i.itemnameenglish,
               poi.orderedquantity,
               poi.receivedquantity,
               poi.estimatedprice,
               poi.supexpirationdate
        FROM   purchaseorderitems poi
        JOIN   item i ON poi.itemid = i.itemid
        WHERE  poi.poid = %s
        """
        return self.fetch_data(query, (poid,))

    # ─────────────────────── inventory & quantities ───────────────────
    def add_items_to_inventory(self, items: list):
        """
        Batch-insert many inventory rows in ONE round-trip and ONE commit.
        """
        rows = [
            (
                int(itm["item_id"]),
                int(itm["quantity"]),
                itm["expiration_date"],
                itm["storage_location"],
                float(itm.get("cost_per_unit", 0.0)),
                itm.get("poid"),
                itm.get("costid"),
            )
            for itm in items
        ]

        sql = """
            INSERT INTO inventory
                  (itemid, quantity, expirationdate,
                   storagelocation,
                   cost_per_unit, poid, costid)   -- datereceived omitted (defaults)
            VALUES %s
        """

        self._ensure_live_conn()
        with self.conn:                        # BEGIN … COMMIT once
            with self.conn.cursor() as cur:
                execute_values(cur, sql, rows)
    def update_received_quantity(self, poid, item_id, qty):
        sql = """
        UPDATE purchaseorderitems
        SET    receivedquantity = %s
        WHERE  poid = %s AND itemid = %s
        """
        self.execute_command(sql, (qty, poid, item_id))

    # ────────────────────────── cost tracking ─────────────────────────
    def insert_poitem_cost(self, poid, item_id, cost_per_unit, qty, note=""):
        sql = """
        INSERT INTO poitemcost (poid, itemid, cost_per_unit,
                                quantity, cost_date, note)
        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, %s)
        RETURNING costid
        """
        res = self.execute_command_returning(sql, (poid, item_id, cost_per_unit, qty, note))
        return int(res[0])          # ← caller now receives costid
        
    def refresh_po_total_cost(self, poid: int):
        sql = """
        UPDATE purchaseorders
        SET    totalcost = COALESCE((
                 SELECT SUM(quantity * cost_per_unit)
                 FROM   poitemcost
                 WHERE  poid = %s
               ),0)
        WHERE  poid = %s
        """
        self.execute_command(sql, (poid, poid))

    # ───────────────────── synthetic‑PO helpers ───────────────────────
    def create_manual_po(self, supplier_id: int, note: str = "") -> int:
        """
        Create a synthetic PO header (status='Completed') and commit.
        Returns the new POID.
        """
        sql = """
        INSERT INTO purchaseorders
              (supplierid, status, orderdate, expecteddelivery,
               actualdelivery, createdby, suppliernote, totalcost)
        VALUES (%s, 'Completed', CURRENT_DATE, CURRENT_DATE,
                CURRENT_DATE, 'ManualReceive', %s, 0.0)
        RETURNING poid
        """
        res = self.execute_command_returning(sql, (supplier_id, note))
        return int(res[0])

    def add_po_item(self, poid: int, item_id: int, qty: int, cost: float):
        sql = """
        INSERT INTO purchaseorderitems
              (poid, itemid, orderedquantity, receivedquantity, estimatedprice)
        VALUES (%s, %s, %s, %s, %s)
        """
        self.execute_command(sql, (poid, item_id, qty, qty, cost))

    # ─────────────────────── PO status helpers ───────────────────────
    def mark_po_completed(self, poid):
        self.execute_command(
            "UPDATE purchaseorders SET status = 'Completed' WHERE poid = %s",
            (poid,)
        )

    # ───────────────────── location helper queries ───────────────────
    def get_items_with_locations_and_expirations(self):
        query = """
        SELECT i.itemid,
               i.itemnameenglish,
               i.barcode,
               inv.storagelocation,
               inv.expirationdate,
               SUM(inv.quantity) AS currentquantity
        FROM   item i
        JOIN   inventory inv ON i.itemid = inv.itemid
        GROUP  BY i.itemid, i.itemnameenglish, i.barcode,
                 inv.storagelocation, inv.expirationdate
        HAVING SUM(inv.quantity) > 0
        """
        return self.fetch_data(query)

    def get_items_without_location(self):
        query = """
        SELECT i.itemid,
               i.itemnameenglish,
               i.barcode,
               COALESCE(inv.quantity,0) AS currentquantity
        FROM   item i
        JOIN   inventory inv ON i.itemid = inv.itemid
        WHERE  inv.storagelocation IS NULL OR inv.storagelocation = ''
        """
        return self.fetch_data(query)

    def update_item_location(self, item_id, new_loc):
        sql = """
        UPDATE inventory
        SET    storagelocation = %s
        WHERE  itemid = %s AND (storagelocation IS NULL OR storagelocation = '')
        """
        self.execute_command(sql, (new_loc, int(item_id)))

    def update_item_location_specific(self, item_id, exp_date, new_loc):
        sql = """
        UPDATE inventory
        SET    storagelocation = %s
        WHERE  itemid = %s AND expirationdate = %s
        """
        self.execute_command(sql, (new_loc, item_id, exp_date))

    # add inside ReceiveHandler (anywhere convenient)
    def get_suppliers(self):
        return self.fetch_data("SELECT supplierid, suppliername FROM supplier "
                               "ORDER BY suppliername")
