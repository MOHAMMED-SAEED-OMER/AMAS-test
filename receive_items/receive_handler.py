# receive_items/receive_handler.py  – MySQL backend (batchid, alias, no ambiguity)
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
        df = self.fetch_data("SELECT COALESCE(MAX(batchid),0)+1 AS next FROM inventory")
        return int(df.iat[0, 0])

    def add_items_to_inventory(self, items: list[dict]) -> None:
        """Insert / upsert with batchid, dates, and unambiguous aliases."""
        if not items:
            return

        batch_id = self._next_batch_id()

        rows = [
            (
                batch_id,
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
            INSERT INTO inventory AS dest
                (batchid, itemid, quantity, expirationdate,
                 storagelocation, cost_per_unit,
                 poid, costid,
                 datereceived, lastupdated)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            AS new
            ON DUPLICATE KEY UPDATE
                dest.quantity   = dest.quantity + new.quantity,
                dest.lastupdated = NOW(),
                dest.batchid    = new.batchid
        """

        self._ensure_live_conn()
        with self.conn.cursor() as cur:
            cur.executemany(sql, rows)
        self.conn.commit()

    # ─────────── remainder of the file (unchanged) ───────────
    # update_received_quantity, cost helpers, PO helpers,
    # location helpers, get_suppliers …
