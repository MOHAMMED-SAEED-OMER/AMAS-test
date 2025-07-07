# receive_items/receive_handler.py  – MySQL backend (fixed batchid, dates)
from db_handler import DatabaseManager


class ReceiveHandler(DatabaseManager):
    """
    DB helpers for the receiving workflow (MySQL).
    """

    # ───────────────────── POs eligible to receive ─────────────────────
    def get_received_pos(self):
        return self.fetch_data(
            """
            SELECT  po.poid,
                    po.expecteddelivery,
                    s.suppliername
            FROM    purchaseorders po
            JOIN    supplier       s ON s.supplierid = po.supplierid
            WHERE   po.status = 'Received'
            """
        )

    def get_po_items(self, poid: int):
        return self.fetch_data(
            """
            SELECT  poi.itemid,
                    i.itemnameenglish,
                    poi.orderedquantity,
                    poi.receivedquantity,
                    poi.estimatedprice,
                    poi.supexpirationdate
            FROM    purchaseorderitems poi
            JOIN    item               i ON i.itemid = poi.itemid
            WHERE   poi.poid = %s
            """,
            (poid,),
        )

    # ─────────────────── inventory & qty updates ──────────────────────
    def _next_batch_id(self) -> int:
        """
        Return MAX(batchid) + 1 (starts at 1 if the table is empty).
        """
        df = self.fetch_data("SELECT COALESCE(MAX(batchid), 0) + 1 AS next FROM inventory")
        return int(df.iat[0, 0])

    def add_items_to_inventory(self, items: list[dict]) -> None:
        """
        Insert / upsert inventory rows for one Receive action.
        • One new batchid is generated and reused for every row.
        • datereceived and lastupdated are set to NOW().
        • Duplicate-key rows get quantity += and lastupdated refreshed.
        """
        if not items:
            return

        batch_id = self._next_batch_id()

        rows = [
            (
                batch_id,                       # NEW
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
                (batchid, itemid, quantity, expirationdate,
                 storagelocation, cost_per_unit,
                 poid, costid,
                 datereceived, lastupdated)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            ON DUPLICATE KEY UPDATE
                quantity    = quantity + VALUES(quantity),
                lastupdated = NOW(),
                batchid     = VALUES(batchid)   -- keep latest batch reference
        """

        self._ensure_live_conn()
        with self.conn.cursor() as cur:
            cur.executemany(sql, rows)
        self.conn.commit()

    def update_received_quantity(self, poid: int, item_id: int, qty: int) -> None:
        self.execute_command(
            """
            UPDATE purchaseorderitems
               SET receivedquantity = %s
             WHERE poid  = %s
               AND itemid = %s
            """,
            (qty, poid, item_id),
        )

    # ──────────────────────── cost tracking ───────────────────────────
    def insert_poitem_cost(
        self,
        poid: int,
        item_id: int,
        cost_per_unit: float,
        qty: int,
        note: str = "",
    ) -> int:
        """
        Insert cost row and return the new costid (AUTO_INCREMENT).
        """
        sql = """
            INSERT INTO poitemcost
                (poid, itemid, cost_per_unit, quantity, cost_date, note)
            VALUES (%s, %s, %s, %s, NOW(), %s)
        """
        self._ensure_live_conn()
        with self.conn.cursor() as cur:
            cur.execute(sql, (poid, item_id, cost_per_unit, qty, note))
            cost_id = cur.lastrowid
        self.conn.commit()
        return int(cost_id)

    def refresh_po_total_cost(self, poid: int) -> None:
        """
        Re-calculate totalcost on a PO from its poitemcost rows.
        """
        self.execute_command(
            """
            UPDATE purchaseorders
               SET totalcost = (
                   SELECT IFNULL(SUM(quantity * cost_per_unit), 0)
                   FROM   poitemcost
                   WHERE  poid = %s
               )
             WHERE poid = %s
            """,
            (poid, poid),
        )

    # ─────────────── synthetic / manual PO helpers ────────────────────
    def create_manual_po(self, supplier_id: int, note: str = "") -> int:
        """
        Create a synthetic PO header (status='Completed') and return POID.
        """
        sql = """
            INSERT INTO purchaseorders
                  (supplierid, status, orderdate, expecteddelivery,
                   actualdelivery, createdby, suppliernote, totalcost)
            VALUES (%s, 'Completed', CURDATE(), CURDATE(),
                    CURDATE(), 'ManualReceive', %s, 0.0)
        """
        self._ensure_live_conn()
        with self.conn.cursor() as cur:
            cur.execute(sql, (supplier_id, note))
            poid = cur.lastrowid
        self.conn.commit()
        return int(poid)

    def add_po_item(self, poid: int, item_id: int, qty: int, cost: float) -> None:
        self.execute_command(
            """
            INSERT INTO purchaseorderitems
                  (poid, itemid, orderedquantity,
                   receivedquantity, estimatedprice)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (poid, item_id, qty, qty, cost),
        )

    # ─────────────────────── PO status helpers ───────────────────────
    def mark_po_completed(self, poid: int) -> None:
        self.execute_command(
            "UPDATE purchaseorders SET status = 'Completed' WHERE poid = %s",
            (poid,),
        )

    # ───────────── location queries & updates ────────────────────────
    def get_items_with_locations_and_expirations(self):
        return self.fetch_data(
            """
            SELECT  i.itemid,
                    i.itemnameenglish,
                    i.barcode,
                    inv.storagelocation,
                    inv.expirationdate,
                    SUM(inv.quantity) AS currentquantity
            FROM    item i
            JOIN    inventory inv ON inv.itemid = i.itemid
            GROUP   BY i.itemid,
                     i.itemnameenglish,
                     i.barcode,
                     inv.storagelocation,
                     inv.expirationdate
            HAVING  SUM(inv.quantity) > 0
            """
        )

    def get_items_without_location(self):
        return self.fetch_data(
            """
            SELECT  i.itemid,
                    i.itemnameenglish,
                    i.barcode,
                    IFNULL(SUM(inv.quantity),0) AS currentquantity
            FROM    item i
            JOIN    inventory inv ON inv.itemid = i.itemid
            WHERE   (inv.storagelocation IS NULL OR inv.storagelocation = '')
            GROUP   BY i.itemid, i.itemnameenglish, i.barcode
            """
        )

    def update_item_location(self, item_id: int, new_loc: str) -> None:
        self.execute_command(
            """
            UPDATE inventory
               SET storagelocation = %s
             WHERE itemid = %s
               AND (storagelocation IS NULL OR storagelocation = '')
            """,
            (new_loc, int(item_id)),
        )

    def update_item_location_specific(
        self, item_id: int, exp_date, new_loc: str
    ) -> None:
        self.execute_command(
            """
            UPDATE inventory
               SET storagelocation = %s
             WHERE itemid        = %s
               AND expirationdate = %s
            """,
            (new_loc, item_id, exp_date),
        )

    # ─────────────── simple helper used by UI tabs ───────────────────
    def get_suppliers(self):
        return self.fetch_data(
            "SELECT supplierid, suppliername FROM supplier ORDER BY suppliername"
        )
