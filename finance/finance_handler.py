# finance/finance_handler.py
import pandas as pd
from db_handler import DatabaseManager

class FinanceHandler(DatabaseManager):
    """
    Finance‑level database helpers.
    """

    # ───────────────────────── Supplier Debt ─────────────────────────
    def get_supplier_debts(self) -> pd.DataFrame:
        """
        Return one row per supplier with the outstanding amount we still owe.
        Sum up totalcost on POs whose status is NOT 'Paid' or 'Cancelled'.
        """
        sql = """
        SELECT
            s.supplierid,
            s.suppliername,
            COALESCE(SUM(po.totalcost), 0) AS amount_owed
        FROM supplier s
        LEFT JOIN purchaseorders po
          ON po.supplierid = s.supplierid
         AND po.status NOT IN ('Paid', 'Cancelled')
        GROUP BY s.supplierid, s.suppliername
        ORDER BY s.suppliername
        """
        return self.fetch_data(sql)

    def get_outstanding_pos_by_supplier(self, supplier_id: int) -> pd.DataFrame:
        """
        Detailed list of still‑unpaid or partially paid POs for a supplier.
        """
        sql = """
        SELECT
          po.poid,
          po.orderdate::date AS order_date,
          po.totalcost,
          COALESCE(SUM(pp.allocatedamount), 0) AS paid_amount,
          po.totalcost - COALESCE(SUM(pp.allocatedamount), 0) AS outstanding_amount
        FROM purchaseorders po
        LEFT JOIN popayments pp
          ON pp.poid = po.poid
        WHERE po.supplierid = %s
        GROUP BY po.poid, po.orderdate, po.totalcost
        HAVING po.totalcost - COALESCE(SUM(pp.allocatedamount), 0) > 0
        ORDER BY po.orderdate
        """
        return self.fetch_data(sql, (supplier_id,))

    # ───────────────────────── Payments API ──────────────────────────
    def create_supplier_payment(
        self,
        supplier_id: int,
        payment_date,
        amount: float,
        method: str,
        notes: str = "",
        payment_type: str | None = None,   # ★ optional field
    ) -> int | None:
        """
        Insert a row into supplierpayments and return the new paymentid.

        If `payment_type` exists, it will be included automatically.
        """
        # Check if supplierpayments.payment_type exists (only once)
        col_exists = hasattr(self, "_has_payment_type")
        if not col_exists:
            q = """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'supplierpayments'
              AND column_name = 'payment_type'
            LIMIT 1;
            """
            self._has_payment_type = not self.fetch_data(q).empty
            col_exists = self._has_payment_type

        base_cols = "supplierid, paymentdate, amount, method, notes"
        base_vals = "%s, %s, %s, %s, %s"
        params = [supplier_id, payment_date, float(amount), method, notes]

        if payment_type and col_exists:
            base_cols += ", payment_type"
            base_vals += ", %s"
            params.append(payment_type)

        sql = f"""
        INSERT INTO supplierpayments ({base_cols})
        VALUES ({base_vals})
        RETURNING paymentid
        """
        res = self.execute_command_returning(sql, params)
        return int(res[0]) if res else None

    def allocate_payment(
        self,
        payment_id: int,
        poid: int,
        allocated_amount: float,
        allocation_status: str,
        return_id: int | None = None,    # ★ NEW
    ) -> None:
        """
        Link a payment to a PO, recording how much was applied and status.
        If return_id is provided, save it too.
        """
        if return_id is not None:
            sql = """
            INSERT INTO popayments
              (paymentid, poid, allocatedamount, allocationstatus, returnid)
            VALUES (%s, %s, %s, %s, %s)
            """
            params = (payment_id, poid, allocated_amount, allocation_status, return_id)
        else:
            sql = """
            INSERT INTO popayments
              (paymentid, poid, allocatedamount, allocationstatus)
            VALUES (%s, %s, %s, %s)
            """
            params = (payment_id, poid, allocated_amount, allocation_status)

        self.execute_command(sql, params)

        # ─────────────────────── Profit Overview ────────────────────────
    def get_profit_overview(self) -> pd.DataFrame:
            """
            Returns one row per item with:
            • on_hand_qty      – current inventory quantity
            • avg_cost         – weighted‑average cost (from poitemcost)
            • sellingprice     – current selling price (Item table)
            • profit_per_unit  – sellingprice − avg_cost
            """
            sql = """
            WITH inv AS (
              SELECT itemid, SUM(quantity) AS on_hand_qty
              FROM inventory
              GROUP BY itemid
            ),
            cost AS (
              SELECT itemid,
                     SUM(quantity * cost_per_unit) / NULLIF(SUM(quantity),0) AS avg_cost
              FROM poitemcost
              GROUP BY itemid
            )
            SELECT
              i.itemid,
              i.itemnameenglish AS itemname,
              COALESCE(inv.on_hand_qty,0)  AS on_hand_qty,
              COALESCE(cost.avg_cost,0)    AS avg_cost,
              COALESCE(i.sellingprice,0)   AS sellingprice,
              COALESCE(i.sellingprice,0) - COALESCE(cost.avg_cost,0)
                                        AS profit_per_unit
            FROM item i
            LEFT JOIN inv  ON inv.itemid  = i.itemid
            LEFT JOIN cost ON cost.itemid = i.itemid
            ORDER BY i.itemnameenglish
            """
            return self.fetch_data(sql)
        
    def get_salary_month_status(self, year: int, month: int):
            """
            Return one row per active employee with:
              expected salary, paid so far, and outstanding
              for the selected month.
            """
            sql = """
                SELECT e.employeeid,
                       e.fullname,
                       e.basicsalary::float                          AS expected,
                       COALESCE((
                           SELECT SUM(sp.amount)
                           FROM   salarypayments sp          -- ← your table
                           WHERE  sp.employeeid   = e.employeeid
                             AND  sp.period_year  = %s
                             AND  sp.period_month = %s
                       ), 0)::float                               AS paid_so_far
                FROM   employee e
                WHERE  e.is_active
                ORDER  BY e.fullname;
            """
            df = self.fetch_data(sql, (year, month))
            if not df.empty:
                df["outstanding"] = df["expected"] - df["paid_so_far"]
            return df
    
    def record_salary_payment(self,
                                  employee_id: int,
                                  period_year: int,
                                  period_month: int,
                                  pay_date,
                                  amount: float,
                                  method: str,
                                  notes: str):
            """
            Insert a salary payment row for a given employee & month.
            """
            sql = """
                INSERT INTO salarypayments           -- ← your table
                    (employeeid, period_year, period_month,
                     amount, pay_date, method, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s);
            """
            self.execute_command(sql, (
                employee_id, period_year, period_month,
                amount, pay_date, method, notes
            ))
