# returns/return_handler.py  ▶︎  MySQL / MariaDB version
import pandas as pd
from db_handler import DatabaseManager


INVALID_DT = "0000-00-00 00:00:00"


class ReturnHandler(DatabaseManager):
    """
    DB helper for supplier returns (MySQL edition).

      • create return header / lines
      • approve return
      • fetch summaries / detail
    """

    # ───────────────────────────────────────────────────────────────
    # Creation helpers
    # ───────────────────────────────────────────────────────────────
    def create_return(
        self,
        *,
        supplier_id: int,
        createdby: str,
        total_return_cost: float,
        creditnote: str = "",
        notes: str = "",
    ) -> int | None:
        sql = """
        INSERT INTO supplierreturns (
            supplierid, creditnote, notes,
            returnstatus, createdby, totalreturncost
        )
        VALUES (%s, %s, %s, 'Pending Approval', %s, %s)
        """
        self._ensure_live_conn()
        with self.conn.cursor() as cur:
            cur.execute(
                sql,
                (supplier_id, creditnote, notes, createdby, total_return_cost),
            )
            self.conn.commit()
            return int(cur.lastrowid)

    # ---------- BULK insert of return items ------------------------
    def add_return_items_bulk(self, items: list[dict]) -> None:
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
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        self._ensure_live_conn()
        with self.conn.cursor() as cur:
            cur.executemany(sql, rows)
            self.conn.commit()

    # shortcut wrapper
    def add_return_item(self, **kw) -> None:
        self.add_return_items_bulk([kw | {"returnid": kw["returnid"]}])

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
    # Look-ups for the UI
    # ───────────────────────────────────────────────────────────────
    def get_purchase_orders_by_supplier(self, supplier_id: int) -> pd.DataFrame:
        sql = """
        SELECT poid,
               DATE(orderdate) AS orderdate,
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
    # Reporting helpers
    # ───────────────────────────────────────────────────────────────
    def _clean_date_expr(self, col: str) -> str:
        """
        Returns a SQL fragment that converts an invalid zero-date in `col`
        to NULL, but keeps valid datetimes as proper DATETIME values.
        """
        # Step 1: turn to CHAR so MySQL doesn't validate right away
        # Step 2: NULLIF against INVALID_DT
        # Step 3: STR_TO_DATE back to DATETIME for sorting / display
        return (
            f"STR_TO_DATE("
            f"NULLIF(CAST({col} AS CHAR), '{INVALID_DT}'), "
            f"'%Y-%m-%d %H:%i:%s')"
        )

    def get_returns_summary(self) -> pd.DataFrame:
        created_expr  = self._clean_date_expr("r.createddate")
        approve_expr  = self._clean_date_expr("r.approvedate")

        sql = f"""
        SELECT r.returnid,
               r.supplierid,
               s.suppliername,
               {created_expr}  AS createddate,
               r.returnstatus,
               r.creditnote,
               r.notes,
               {approve_expr}  AS approvedate
          FROM supplierreturns r
          JOIN supplier s ON s.supplierid = r.supplierid
         ORDER BY createddate DESC
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
        created_expr  = self._clean_date_expr("createddate")
        approve_expr  = self._clean_date_expr("approvedate")
        sql = f"""
        SELECT *,
               {created_expr}  AS createddate,
               {approve_expr}  AS approvedate
          FROM supplierreturns
         WHERE returnid = %s
        """
        return self.fetch_data(sql, (returnid,))

    # ───────────────────────── inventory adjustment ────────────────
    def reduce_inventory(self, *, itemid: int, expiredate: str, qty: int) -> None:
        sql = """
        UPDATE inventory
           SET quantity = quantity - %s
         WHERE itemid = %s
           AND expirationdate = %s
        """
        self.execute_command(sql, (qty, itemid, expiredate))
