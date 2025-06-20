# cashier/cashier_handler.py
import pandas as pd
from datetime import date
from psycopg2.extras import execute_values
from db_handler import DatabaseManager


class CashierHandler(DatabaseManager):
    """
    DB helpers for POS:
      • create sale header & line items
      • keep shelf stock in sync
    """

    # ───────────────────── sale header ─────────────────────
    def create_sale_record(
        self,
        total_amount,
        discount_rate,
        total_discount,
        final_amount,
        payment_method,
        cashier,
        notes="",
        original_saleid=None,
    ) -> int | None:
        sql = """
        INSERT INTO sales (
            totalamount, discountrate, totaldiscount, finalamount,
            paymentmethod, cashier, notes, original_saleid
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING saleid;
        """
        res = self.execute_command_returning(
            sql,
            (
                float(total_amount),
                float(discount_rate),
                float(total_discount),
                float(final_amount),
                payment_method,
                cashier,
                notes,
                original_saleid,
            ),
        )
        return int(res[0]) if res else None

    # ───────────────────── line items (batch) ─────────────────────
    def add_sale_items(self, saleid, items_list):
        rows = [
            (
                int(saleid),
                int(it["itemid"]),
                int(it["quantity"]),
                float(it["unitprice"]),
                float(it["totalprice"]),
            )
            for it in items_list
        ]
        sql = """
            INSERT INTO salesitems
                  (saleid, itemid, quantity, unitprice, totalprice)
            VALUES %s
        """
        self._ensure_live_conn()
        with self.conn.cursor() as cur:
            execute_values(cur, sql, rows)
        self.conn.commit()

    # ───────────────────── shelf stock update ─────────────────────
    def reduce_shelf_stock(self, itemid, quantity_sold):
        """
        Subtract qty from oldest shelf layer. If the item is
        not on shelf yet, create a negative row so stock never "hides".
        """
        itemid_py   = int(itemid)
        qty_py      = int(quantity_sold)

        batch = self.fetch_data(
            """
            SELECT shelfid, quantity
            FROM   shelf
            WHERE  itemid = %s
            ORDER  BY expirationdate
            LIMIT 1;
            """,
            (itemid_py,),
        )

        if not batch.empty:
            shelfid = int(batch.iloc[0]["shelfid"])
            new_qty = int(batch.iloc[0]["quantity"]) - qty_py
            self.execute_command(
                """
                UPDATE shelf
                   SET quantity    = %s,
                       lastupdated = CURRENT_TIMESTAMP
                 WHERE shelfid     = %s;
                """,
                (new_qty, shelfid),
            )
        else:
            # pull earliest expiry from inventory, else today
            exp_row = self.fetch_data(
                """
                SELECT expirationdate
                  FROM inventory
                 WHERE itemid = %s
                 ORDER  BY expirationdate
                 LIMIT 1;
                """,
                (itemid_py,),
            )
            expiry = exp_row.iloc[0]["expirationdate"] if not exp_row.empty else date.today()

            self.execute_command(
                """
                INSERT INTO shelf
                      (itemid, expirationdate, quantity, lastupdated, notes)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP,
                        'Auto-created negative stock by cashier sale');
                """,
                (itemid_py, expiry, -qty_py),
            )
            # ⚠️ no ShelfEntries write — selling does not log movements

    # ───────────────────── finalize POS / return ─────────────────────
    def finalize_sale(
        self,
        cart_items,
        discount_rate,
        payment_method,
        cashier,
        notes="",
        original_saleid=None,
    ):
        # 1) totals
        subtotal = sum(float(ci["quantity"]) * float(ci["sellingprice"]) for ci in cart_items)
        total_disc = round(subtotal * float(discount_rate) / 100, 2)
        final_amt  = round(subtotal - total_disc, 2)

        # 2) (optional) validate return quantities …
        if payment_method == "Return" and original_saleid:
            self._validate_return_quantities(cart_items, original_saleid)

        # 3) header
        saleid = self.create_sale_record(
            subtotal,
            discount_rate,
            total_disc,
            final_amt,
            payment_method,
            cashier,
            notes,
            original_saleid,
        )
        if saleid is None:
            return None

        # 4) line items
        lines = []
        for ci in cart_items:
            qty  = int(ci["quantity"])
            unit = float(ci["sellingprice"])
            lines.append(
                {
                    "itemid": ci["itemid"],
                    "quantity": qty,
                    "unitprice": unit,
                    "totalprice": round(qty * unit, 2),
                }
            )
        self.add_sale_items(saleid, lines)

        # 5) shelf deduction
        for ci in cart_items:
            self.reduce_shelf_stock(ci["itemid"], abs(int(ci["quantity"])))

        return saleid

    # ---------------- internal helper --------------------------------
    def _validate_return_quantities(self, cart_items, original_saleid):
        """
        Ensure cumulative returns never exceed original sold qty.
        """
        orig = self.fetch_data(
            "SELECT itemid, quantity FROM salesitems WHERE saleid = %s",
            (original_saleid,),
        )
        if orig.empty:
            raise Exception("Original sale items not found.")

        sold = {r.itemid: float(r.quantity) for r in orig.itertuples()}

        already = self.fetch_data(
            """
            SELECT itemid, SUM(ABS(quantity)) AS returned
            FROM salesitems
            WHERE saleid IN (
                SELECT saleid FROM sales WHERE original_saleid = %s
            )
            GROUP BY itemid;
            """,
            (original_saleid,),
        )
        returned = {r.itemid: float(r.returned) for r in already.itertuples()}

        for ci in cart_items:
            iid = int(ci["itemid"])
            req = abs(float(ci["quantity"]))
            allowed = sold.get(iid, 0) - returned.get(iid, 0)
            if req > allowed:
                raise Exception(f"Return qty for item {iid} exceeds allowed ({allowed}).")

    # ───────────────────── reporting helper ─────────────────────
    def get_sale_details(self, saleid):
        sale_df  = self.fetch_data("SELECT * FROM sales WHERE saleid = %s", (saleid,))
        items_df = self.fetch_data(
            """
            SELECT si.*, i.itemnameenglish AS itemname
              FROM salesitems si
              JOIN item i ON i.itemid = si.itemid
             WHERE si.saleid = %s;
            """,
            (saleid,),
        )
        return sale_df, items_df
