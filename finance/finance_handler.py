# finance/finance_handler.py  – MySQL backend
from __future__ import annotations

import datetime
import decimal
import pandas as pd

from db_handler import DatabaseManager


class FinanceHandler(DatabaseManager):
    """
    Finance-level helpers for the AMAS Finance module (MySQL edition).

    Key points
    ----------
    • `_ensure_live_conn()` quietly pings / re-opens the MySQL connection
      before every write so Streamlit’s long-running sessions never hit
      “MySQL server has gone away”.
    • `create_supplier_payment()` now:
        – Upgrades a date-only object to a full `datetime` (using the
          current local time) so you always store an accurate timestamp.
        – Relies on the table’s DEFAULT `'Standard'` when the UI leaves
          `payment_type` blank, but still lets callers override it.
    """

    # ───────────────────────── internal guard ─────────────────────────
    def _ensure_live_conn(self) -> None:
        """Ping the connection; reconnect if the socket was dropped."""
        if getattr(self, "conn", None) is not None:
            try:
                self.conn.ping(reconnect=True)       # PyMySQL & mysql-connector
                return
            except Exception:                        # pragma: no cover
                pass

        # Ask the DatabaseManager base for a new handle
        if hasattr(self, "_connect"):
            self.conn = self._connect()
        else:
            self.conn = self.connect()  # type: ignore[attr-defined]

    # ───────────────────── Supplier Debt ─────────────────────
    def get_supplier_debts(self) -> pd.DataFrame:
        sql = """
            SELECT  s.supplierid,
                    s.suppliername,
                    COALESCE(SUM(po.totalcost), 0) AS amount_owed
            FROM    `supplier` s
            LEFT JOIN `purchaseorders` po
                   ON po.supplierid = s.supplierid
                  AND po.status NOT IN ('Paid', 'Cancelled')
            GROUP BY s.supplierid, s.suppliername
            ORDER BY s.suppliername;
        """
        return self.fetch_data(sql)

    def get_outstanding_pos_by_supplier(self, supplier_id: int) -> pd.DataFrame:
        sql = """
            SELECT  po.poid,
                    DATE(po.orderdate)                   AS order_date,
                    po.totalcost,
                    COALESCE(SUM(pp.allocatedamount), 0) AS paid_amount,
                    po.totalcost - COALESCE(SUM(pp.allocatedamount), 0)
                                                     AS outstanding_amount
            FROM    `purchaseorders` po
            LEFT JOIN `popayments`   pp ON pp.poid = po.poid
            WHERE   po.supplierid = %s
            GROUP BY po.poid, po.orderdate, po.totalcost
            HAVING  outstanding_amount > 0
            ORDER BY po.orderdate;
        """
        return self.fetch_data(sql, (supplier_id,))

    # ───────────────────── Supplier Payments ─────────────────────
    def create_supplier_payment(
        self,
        *,
        supplier_id: int,
        payment_date,
        amount: float | decimal.Decimal,
        method: str,
        notes: str = "",
        payment_type: str | None = None,
    ) -> int | None:
        """
        Insert a row into `supplierpayments` and return its AUTO_INCREMENT id.

        • If the user picked only a calendar date (no time), we add the current
          time so `paymentdate` becomes a proper timestamp.
        • `payment_type` is only included when the caller supplies a value;
          otherwise we rely on the table default 'Standard'.
        """
        # ── Normalise `payment_date` ───────────────────────────────────
        if (
            isinstance(payment_date, datetime.date)
            and not isinstance(payment_date, datetime.datetime)
        ):
            payment_date = datetime.datetime.combine(
                payment_date, datetime.datetime.now().time()
            )

        # ── Detect once whether the column exists ──────────────────────
        if not hasattr(self, "_has_payment_type"):
            probe = """
                SELECT 1
                FROM   information_schema.columns
                WHERE  table_schema = DATABASE()
                  AND  table_name   = 'supplierpayments'
                  AND  column_name  = 'payment_type'
                LIMIT 1;
            """
            self._has_payment_type = not self.fetch_data(probe).empty

        cols = ["supplierid", "paymentdate", "amount", "method", "notes"]
        vals = [
            supplier_id,
            payment_date,
            decimal.Decimal(str(amount)),
            method,
            notes,
        ]

        # Only send payment_type if the caller set it (otherwise leave column
        # out and let MySQL apply its DEFAULT 'Standard')
        if payment_type is not None and self._has_payment_type:
            cols.append("payment_type")
            vals.append(payment_type)

        placeholders = ", ".join(["%s"] * len(cols))
        col_list     = ", ".join(f"`{c}`" for c in cols)

        sql = f"""
            INSERT INTO `supplierpayments` ({col_list})
            VALUES ({placeholders});
        """

        # ── Execute ───────────────────────────────────────────────────
        self._ensure_live_conn()
        with self.conn.cursor() as cur:                # type: ignore[attr-defined]
            cur.execute(sql, vals)
            pay_id = cur.lastrowid
        self.conn.commit()

        return int(pay_id) if pay_id else None

    def allocate_payment(
        self,
        payment_id: int,
        poid: int,
        allocated_amount: float | decimal.Decimal,
        allocation_status: str,
        return_id: int | None = None,
    ) -> None:
        """Link a payment to a PO (and optionally a Return)."""
        sql = """
            INSERT INTO `popayments`
                   (paymentid, poid, allocatedamount, allocationstatus, returnid)
            VALUES (%s, %s, %s, %s, %s);
        """
        params = (
            payment_id,
            poid,
            decimal.Decimal(str(allocated_amount)),
            allocation_status,
            return_id,
        )
        self.execute_command(sql, params)

    # ───────────────────── Profit Overview ─────────────────────
    def get_profit_overview(self) -> pd.DataFrame:
        sql = """
            WITH inv AS (
                SELECT itemid, SUM(quantity) AS on_hand_qty
                FROM   `inventory`
                GROUP  BY itemid
            ),
            cost AS (
                SELECT itemid,
                       SUM(quantity * cost_per_unit) /
                       NULLIF(SUM(quantity), 0) AS avg_cost
                FROM   `poitemcost`
                GROUP  BY itemid
            )
            SELECT  i.itemid,
                    i.itemnameenglish                 AS itemname,
                    COALESCE(inv.on_hand_qty, 0)      AS on_hand_qty,
                    COALESCE(cost.avg_cost, 0)        AS avg_cost,
                    COALESCE(i.sellingprice, 0)       AS sellingprice,
                    COALESCE(i.sellingprice, 0) -
                    COALESCE(cost.avg_cost,   0)      AS profit_per_unit
            FROM    `item` i
            LEFT JOIN inv  ON inv.itemid  = i.itemid
            LEFT JOIN cost ON cost.itemid = i.itemid
            ORDER BY i.itemnameenglish;
        """
        return self.fetch_data(sql)

    # ───────────────────── Salary helpers ─────────────────────
    def get_salary_month_status(self, year: int, month: int) -> pd.DataFrame:
        sql = """
            SELECT  e.employeeid,
                    e.fullname,
                    e.basicsalary                     AS expected,
                    COALESCE((
                        SELECT SUM(sp.amount)
                        FROM   `salarypayments` sp
                        WHERE  sp.employeeid   = e.employeeid
                          AND  sp.period_year  = %s
                          AND  sp.period_month = %s
                    ), 0)                              AS paid_so_far
            FROM    `employee` e
            WHERE   e.is_active = 1
            ORDER BY e.fullname;
        """
        df = self.fetch_data(sql, (year, month))
        if not df.empty:
            df["outstanding"] = df["expected"] - df["paid_so_far"]
        return df

    def record_salary_payment(
        self,
        *,
        employee_id: int,
        period_year: int,
        period_month: int,
        pay_date,
        amount: float | decimal.Decimal,
        method: str,
        notes: str,
    ) -> None:
        sql = """
            INSERT INTO `salarypayments`
                   (employeeid, period_year, period_month,
                    amount, pay_date, method, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
        """
        params = (
            employee_id,
            period_year,
            period_month,
            decimal.Decimal(str(amount)),
            pay_date,
            method,
            notes,
        )
        self.execute_command(sql, params)
