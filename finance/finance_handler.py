# finance/finance_handler.py  – MySQL backend
import pandas as pd

from db_handler import DatabaseManager


class FinanceHandler(DatabaseManager):
    """
    Finance-level DB helpers (works with MySQL).
    """

    # ───────────────────────── Supplier Debt ─────────────────────────
    def get_supplier_debts(self) -> pd.DataFrame:
        """
        One row per supplier with the outstanding amount we still owe:
        Sum of purchaseorders.totalcost where status not Paid/Cancelled.
        """
        sql = """
            SELECT  s.supplierid,
                    s.suppliername,
                    COALESCE(SUM(po.totalcost), 0) AS amount_owed
            FROM    `supplier` s
            LEFT JOIN `purchaseorders` po
                   ON po.supplierid = s.supplierid
                  AND po.status NOT IN ('Paid', 'Cancelled')
            GROUP BY s.supplierid, s.suppliername
            ORDER BY s.suppliername
        """
        return self.fetch_data(sql)

    def get_outstanding_pos_by_supplier(self, supplier_id: int) -> pd.DataFrame:
        """
        Detailed list of still-unpaid / partially-paid POs for a supplier.
        """
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
            ORDER BY po.orderdate
        """
        return self.fetch_data(sql, (supplier_id,))

    # ───────────────────────── Payments API ──────────────────────────
    def create_supplier_payment(
        self,
        *,
        supplier_id: int,
        payment_date,
        amount: float,
        method: str,
        notes: str = "",
        payment_type: str | None = None,  # optional column
    ) -> int | None:
        """
        Insert a row into supplierpayments and return the new paymentid.
        Handles optional payment_type column if present.
        """
        # Discover column existence only once
        if not hasattr(self, "_has_payment_type"):
            q = """
                SELECT 1
                FROM   information_schema.columns
                WHERE  table_name = 'supplierpayments'
                  AND  column_name = 'payment_type'
                LIMIT 1
            """
            self._has_payment_type = not self.fetch_data(q).empty

        cols = ["supplierid", "paymentdate", "amount", "method", "notes"]
        vals = [supplier_id, payment_date, float(amount), method, notes]

        if payment_type and self._has_payment_type:
            cols.append("payment_type")
            vals.append(payment_type)

        placeholders = ", ".join(["%s"] * len(cols))
        col_list     = ", ".join(cols)

        sql = f"INSERT INTO `supplierpayments` ({col_list}) VALUES ({placeholders})"

        # MySQL ⇒ grab AUTO_INCREMENT via lastrowid
        self._ensure_live_conn()
        with self.conn.cursor() as cur:
            cur.execute(sql, vals)
            pay_id = cur.lastrowid
        self.conn.commit()

        return int(pay_id) if pay_id else None

    def allocate_payment(
        self,
        payment_id: int,
        poid: int,
        allocated_amount: float,
        allocation_status: str,
        return_id: int | None = None,
    ) -> None:
        """
        Link a payment to a PO (and optional Return) in popayments.
        """
        if return_id is not None:
            sql = """
                INSERT INTO `popayments`
                    (paymentid, poid, allocatedamount, allocationstatus, returnid)
                VALUES (%s, %s, %s, %s, %s)
            """
            params = (payment_id, poid, allocated_amount, allocation_status, return_id)
        else:
            sql = """
                INSERT INTO `popayments`
                    (paymentid, poid, allocatedamount, allocationstatus)
                VALUES (%s, %s, %s, %s)
            """
            params = (payment_id, poid, allocated_amount, allocation_status)
        self.execute_command(sql, params)

    # ─────────────────────── Profit Overview ────────────────────────
    def get_profit_overview(self) -> pd.DataFrame:
        """
        One row per item with on-hand qty, avg cost, selling price, profit.
        """
        sql = """
            WITH inv AS (
                SELECT itemid,
                       SUM(quantity) AS on_hand_qty
                FROM   `inventory`
                GROUP  BY itemid
            ),
            cost AS (
                SELECT itemid,
                       SUM(quantity * cost_per_unit) /
                       NULLIF(SUM(quantity), 0)  AS avg_cost
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
            ORDER BY i.itemnameenglish
        """
        return self.fetch_data(sql)

    # ─────────────────── Salary / Payroll helpers ───────────────────
    def get_salary_month_status(self, year: int, month: int) -> pd.DataFrame:
        """
        One row per active employee with expected salary, paid so far, outstanding.
        """
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
            WHERE   e.is_active
            ORDER BY e.fullname
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
        amount: float,
        method: str,
        notes: str,
    ) -> None:
        """
        Insert a salary payment row for a given employee & month.
        """
        sql = """
            INSERT INTO `salarypayments`
                (employeeid, period_year, period_month,
                 amount, pay_date, method, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        self.execute_command(
            sql,
            (
                employee_id,
                period_year,
                period_month,
                float(amount),
                pay_date,
                method,
                notes,
            ),
        )
