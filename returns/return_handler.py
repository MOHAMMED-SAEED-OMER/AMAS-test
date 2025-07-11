# returns/return_handler.py  – MySQL edition
from __future__ import annotations

import decimal
from typing import Iterable

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

    # ───────────────────── internal connection guard ──────────────────────
    def _ensure_live_conn(self) -> None:
        """Ping the connection; reconnect if the socket was dropped."""
        if getattr(self, "conn", None) is not None:
            try:
                self.conn.ping(reconnect=True)
                return
            except Exception:  # pragma: no cover
                pass

        # Have DatabaseManager reopen the handle
        if hasattr(self, "_connect"):
            self.conn = self._connect()
        else:
            self.conn = self.connect()  # type: ignore[attr-defined]

    # ───────────────────── small helper for query results ─────────────────
    @staticmethod
    def _as_float(df: pd.DataFrame, cols: Iterable[str]) -> pd.DataFrame:
        for c in cols:
            if c in df.columns:
                df[c] = df[c].astype(float)
        return df

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
        with self.conn.cursor() as cur:                 # type: ignore[attr-defined]
            cur.execute(
                sql,
                (
                    supplier_id,
                    creditnote,
                    notes,
                    createdby,
                    decimal.Decimal(str(total_return_cost)),
                ),
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
                decimal.Decimal(str(it["itemprice"])),
                decimal.Decimal(str(it["quantity"])) * decimal.Decimal(
                    str(it["itemprice"])
                ),
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
        with self.conn.cursor() as cur:                 # type: ignore[attr-defined]
            cur.executemany(sql, rows)
            self.conn.commit()

    def add_return_item(self, **kw) -> None:
        """Thin wrapper around bulk insert for a single line."""
        self.add_return_items_bulk([kw])

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
        df = self.fetch_data(sql, (supplier_id,))
        return self._as_float(df, ["totalcost"])

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
    @staticmethod
    def _clean_date_expr(col: str) -> str:
        """
        Return a SQL fragment that yields NULL when `col` holds the illegal
        zero-date literal, otherwise the original DATETIME value.
        """
        return (
            f"CASE WHEN CAST({col} AS CHAR) = '{INVALID_DT}' "
            f"THEN NULL ELSE {col} END"
        )

    def get_returns_summary(self) -> pd.DataFrame:
        created  = self._clean_date_expr("r.createddate")
        approved = self._clean_date_expr("r.approvedate")

        sql = f"""
        SELECT r.returnid,
               r.supplierid,
               s.suppliername,
               {created}  AS createddate,
               r.returnstatus,
               r.creditnote,
               r.notes,
               {approved} AS approvedate
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
        df = self.fetch_data(sql, (returnid,))
        return self._as_float(df, ["itemprice", "totalcost", "quantity"])

    def get_return_header(self, returnid: int) -> pd.DataFrame:
        created  = self._clean_date_expr("createddate")
        approved = self._clean_date_expr("approvedate")

        sql = f"""
        SELECT * ,
               {created}  AS createddate,
               {approved} AS approvedate
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
