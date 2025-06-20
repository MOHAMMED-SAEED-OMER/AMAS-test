# returns/return_handler.py
import pandas as pd
from db_handler import DatabaseManager
from psycopg2.extras import execute_values      # <-- NEW

class ReturnHandler(DatabaseManager):
    """
    Handles all DB work for supplier returns:
      • create return header / items
      • approve return
      • fetch summaries & detail
      • helper look-ups (POs + PO items)
    """

    # ───────────────────────────────────────────────────────────────
    # Create & Edit
    # ───────────────────────────────────────────────────────────────
    def create_return(
        self,
        *,
        supplier_id: int,
        createdby: str,
        total_return_cost: float,
        creditnote: str = "",
        notes: str = "",
    ) -> int:
        """
        Insert a new row in supplierreturns.  Returns the new returnid.
        """
        sql = """
        INSERT INTO supplierreturns (
            supplierid,
            creditnote,
            notes,
            returnstatus,
            createdby,
            totalreturncost
        )
        VALUES (%s, %s, %s, 'Pending Approval', %s, %s)
        RETURNING returnid;
        """
        res = self.execute_command_returning(
            sql, (supplier_id, creditnote, notes, createdby, total_return_cost)
        )
        return int(res[0]) if res else None

    # ----------- NEW: batch insert for many return lines ------------
    def add_return_items_bulk(self, items: list[dict]) -> None:
        """
        Batch-insert many rows into supplierreturnitems in ONE transaction.
        Each dict needs keys:
            returnid, itemid, quantity, itemprice
        Optional keys:
            reason, poid, expiredate
        """
        if not items:
            return

        rows = [
            (
                it["returnid"],
                it["itemid"],
                it["quantity"],
                it["itemprice"],
                float(it["quantity"]) * float(it["itemprice"]),
                it.get("reason", ""),
                it.get("poid"),
                it.get("expiredate"),
            )
            for it in items
        ]

        sql = """
            INSERT INTO supplierreturnitems (
                returnid, itemid, quantity,
                itemprice, totalcost, reason,
                poid, expirationdate
            )
            VALUES %s
        """

        self._ensure_live_conn()
        with self.conn:                        # BEGIN … COMMIT once
            with self.conn.cursor() as cur:
                execute_values(cur, sql, rows)

    # ---- backward-compatible single-row helper (calls bulk) --------
    def add_return_item(
        self,
        *,
        returnid: int,
        itemid: int,
        quantity: float,
        itemprice: float,
        reason: str = "",
        poid: int = None,
        expiredate: str = None,
    ) -> None:
        """
        Add ONE line into supplierreturnitems.
        (Now implemented via bulk helper for efficiency.)
        """
        self.add_return_items_bulk(
            [
                dict(
                    returnid=returnid,
                    itemid=itemid,
                    quantity=quantity,
                    itemprice=itemprice,
                    reason=reason,
                    poid=poid,
                    expiredate=expiredate,
                )
            ]
        )

    # ───────────────────────────────────────────────────────────────
    # Approval
    # ───────────────────────────────────────────────────────────────
    def approve_return(self, returnid: int, creditnote: str) -> None:
        sql = """
        UPDATE supplierreturns
           SET returnstatus = 'Approved',
               creditnote   = %s,
               approvedate  = CURRENT_TIMESTAMP
         WHERE returnid     = %s
        """
        self.execute_command(sql, (creditnote, returnid))

    # ───────────────────────────────────────────────────────────────
    # Look-ups for UI
    # ───────────────────────────────────────────────────────────────
    def get_purchase_orders_by_supplier(self, supplier_id: int) -> pd.DataFrame:
        sql = """
        SELECT poid,
               orderdate::date   AS orderdate,
               totalcost,
               status
          FROM purchaseorders
         WHERE supplierid = %s
         ORDER BY orderdate DESC
        """
        return self.fetch_data(sql, (supplier_id,))

    def get_po_items(self, poid: int) -> pd.DataFrame:
        sql = """
        SELECT poi.itemid,
               i.itemnameenglish,
               poi.orderedquantity,
               poi.receivedquantity
          FROM purchaseorderitems poi
          JOIN item i ON i.itemid = poi.itemid
         WHERE poi.poid = %s
         ORDER BY i.itemnameenglish
        """
        return self.fetch_data(sql, (poid,))

    # ───────────────────────────────────────────────────────────────
    # Reporting
    # ───────────────────────────────────────────────────────────────
    def get_returns_summary(self) -> pd.DataFrame:
        sql = """
        SELECT r.returnid,
               r.supplierid,
               s.suppliername,
               r.createddate,
               r.returnstatus,
               r.creditnote,
               r.notes,
               r.approvedate
          FROM supplierreturns r
          JOIN supplier s ON s.supplierid = r.supplierid
         ORDER BY r.createddate DESC
        """
        return self.fetch_data(sql)

    def get_return_items(self, returnid: int) -> pd.DataFrame:
        sql = """
        SELECT sri.itemid,
               i.itemnameenglish,
               sri.quantity,
               sri.itemprice,
               sri.totalcost,
               sri.reason,
               sri.poid,
               sri.expirationdate
          FROM supplierreturnitems sri
          JOIN item i ON i.itemid = sri.itemid
         WHERE sri.returnid = %s
         ORDER BY i.itemnameenglish
        """
        return self.fetch_data(sql, (returnid,))

    def get_return_header(self, returnid: int) -> pd.DataFrame:
        return self.fetch_data(
            "SELECT * FROM supplierreturns WHERE returnid = %s",
            (returnid,),
        )

    # ───────────────────────── inventory update ─────────────────────
    def reduce_inventory(
        self, *, itemid: int, expiredate: str, qty: int
    ) -> None:
        sql = """
        UPDATE inventory
           SET quantity = quantity - %s
         WHERE itemid = %s
           AND expirationdate = %s
        """
        self.execute_command(sql, (qty, itemid, expiredate))
