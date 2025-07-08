# selling_area/shelf_handler.py
import pandas as pd
from db_handler import DatabaseManager


class ShelfHandler(DatabaseManager):
    """Handles database operations related to the Shelf (Selling Area)."""

    # ───────────────────────── shelf queries ─────────────────────────
    def get_shelf_items(self):
        query = """
        SELECT 
            s.shelfid,
            s.itemid,
            i.itemnameenglish AS itemname,
            s.quantity,
            s.expirationdate,
            s.cost_per_unit,
            s.lastupdated
        FROM   shelf s
        JOIN   item  i ON s.itemid = i.itemid
        ORDER  BY i.itemnameenglish, s.expirationdate;
        """
        return self.fetch_data(query)

    # ────────────────────── recent shelf location ───────────────────
    def last_locid(self, itemid: int) -> str | None:
        """
        Most recent non-NULL `locid` where this item was placed
        (from `shelfentries`). Returns None if not found.
        """
        df = self.fetch_data(
            """
            SELECT locid
            FROM   shelfentries
            WHERE  itemid = %s
              AND  locid  IS NOT NULL
            ORDER  BY entrydate DESC
            LIMIT 1
            """,
            (itemid,),
        )
        return None if df.empty else str(df.iloc[0, 0])

    # ───────────────── add / update shelf (+ log) ───────────────────
    def add_to_shelf(
        self,
        itemid: int,
        expirationdate,
        quantity: int,
        created_by: str,
        cost_per_unit: float,
        cur=None,          # optional open cursor for transaction use
    ):
        """
        Upsert (insert or increment) a shelf row and log the move.
        MySQL 8-compatible `ON DUPLICATE KEY UPDATE`.
        The UNIQUE/PK on `shelf` must include (itemid, expirationdate, cost_per_unit).
        """
        own_cursor = False
        if cur is None:
            self._ensure_live_conn()
            cur = self.conn.cursor()
            own_cursor = True

        itemid = int(itemid)
        qty    = int(quantity)
        cost   = float(cost_per_unit)

        # 1️⃣ upsert / increment shelf
        cur.execute(
            """
            INSERT INTO shelf (itemid, expirationdate, quantity, cost_per_unit)
            VALUES (%s, %s, %s, %s) AS new
            ON DUPLICATE KEY UPDATE
                quantity    = shelf.quantity + new.quantity,
                lastupdated = CURRENT_TIMESTAMP
            """,
            (itemid, expirationdate, qty, cost),
        )

        # 2️⃣ movement log
        cur.execute(
            """
            INSERT INTO shelfentries (itemid, expirationdate, quantity, createdby)
            VALUES (%s, %s, %s, %s)
            """,
            (itemid, expirationdate, qty, created_by),
        )

        if own_cursor:
            self.conn.commit()
            cur.close()

    # ───────────────────── inventory look-ups ──────────────────────
    def get_inventory_items(self):
        query = """
        SELECT 
            inv.itemid,
            i.itemnameenglish AS itemname,
            inv.quantity,
            inv.expirationdate,
            inv.storagelocation,
            inv.cost_per_unit
        FROM   inventory inv
        JOIN   item       i ON inv.itemid = i.itemid
        WHERE  inv.quantity > 0
        ORDER  BY i.itemnameenglish, inv.expirationdate;
        """
        return self.fetch_data(query)

    # ───────── fast transfer from inventory (one transaction) ──────
    def transfer_from_inventory(
        self,
        itemid: int,
        expirationdate,
        quantity: int,
        cost_per_unit: float,
        created_by: str,
    ):
        """
        Move one cost layer from Inventory → Shelf inside ONE transaction.
        """
        itemid = int(itemid)
        qty    = int(quantity)
        cost   = float(cost_per_unit)

        self._ensure_live_conn()
        with self.conn:                # BEGIN … COMMIT
            with self.conn.cursor() as cur:
                # 1. decrement that exact layer in inventory
                cur.execute(
                    """
                    UPDATE inventory
                    SET    quantity = quantity - %s
                    WHERE  itemid         = %s
                      AND  expirationdate = %s
                      AND  cost_per_unit  = %s
                      AND  quantity >= %s
                    """,
                    (qty, itemid, expirationdate, cost, qty),
                )
                # 2. upsert into shelf + log entry
                self.add_to_shelf(
                    itemid,
                    expirationdate,
                    qty,
                    created_by,
                    cost,
                    cur=cur,           # reuse open cursor
                )

    # ───────────────────── alerts / misc helpers ───────────────────
    def get_low_shelf_stock(self, threshold=10):
        query = """
        SELECT 
            s.itemid,
            i.itemnameenglish AS itemname,
            s.quantity,
            s.expirationdate
        FROM   shelf s
        JOIN   item  i ON s.itemid = i.itemid
        WHERE  s.quantity <= %s
        ORDER  BY s.quantity ASC;
        """
        return self.fetch_data(query, (threshold,))

    def get_inventory_by_barcode(self, barcode):
        query = """
        SELECT 
            inv.itemid,
            i.itemnameenglish AS itemname,
            inv.quantity,
            inv.expirationdate,
            inv.cost_per_unit
        FROM   inventory inv
        JOIN   item       i ON inv.itemid = i.itemid
        WHERE  i.barcode = %s AND inv.quantity > 0
        ORDER  BY inv.expirationdate;
        """
        return self.fetch_data(query, (barcode,))

    # -------------- item master helpers ----------------------------
    def get_all_items(self):
        query = """
        SELECT 
            itemid,
            itemnameenglish AS itemname,
            shelfthreshold,
            shelfaverage
        FROM item
        ORDER BY itemnameenglish;
        """
        df = self.fetch_data(query)
        if not df.empty:
            df["shelfthreshold"] = df["shelfthreshold"].astype("Int64")
            df["shelfaverage"]   = df["shelfaverage"].astype("Int64")
        return df

    def update_shelf_settings(self, itemid, new_threshold, new_average):
        query = """
        UPDATE item
        SET    shelfthreshold = %s,
               shelfaverage   = %s
        WHERE  itemid = %s;
        """
        self.execute_command(query, (int(new_threshold), int(new_average), int(itemid)))

    def get_shelf_quantity_by_item(self):
        query = """
        SELECT 
            i.itemid,
            i.itemnameenglish AS itemname,
            COALESCE(SUM(s.quantity), 0) AS totalquantity,
            i.shelfthreshold,
            i.shelfaverage
        FROM   item  i
        LEFT JOIN shelf s ON i.itemid = s.itemid
        GROUP  BY i.itemid, i.itemnameenglish, i.shelfthreshold, i.shelfaverage
        ORDER  BY i.itemnameenglish;
        """
        df = self.fetch_data(query)
        if not df.empty:
            df["shelfthreshold"] = df["shelfthreshold"].astype("Int64")
            df["shelfaverage"]   = df["shelfaverage"].astype("Int64")
            df["totalquantity"]  = df["totalquantity"].astype(int)
        return df

    # ───────── shortage resolver (for transfer) ─────────
    def resolve_shortages(self, *, itemid: int, qty_need: int, user: str) -> int:
        """
        Deduct open shortages for this itemid (FIFO). Returns qty still to place.
        """
        rows = self.fetch_data(
            """
            SELECT shortageid, shortage_qty
            FROM   shelf_shortage
            WHERE  itemid = %s AND resolved = FALSE
            ORDER  BY logged_at
            """,
            (itemid,),
        )

        remaining = qty_need
        for r in rows.itertuples():
            if remaining == 0:
                break
            take = min(remaining, int(r.shortage_qty))

            # shrink or resolve the shortage row
            self.execute_command(
                """
                UPDATE shelf_shortage
                SET    shortage_qty = shortage_qty - %s,
                       resolved      = (shortage_qty - %s = 0),
                       resolved_qty  = COALESCE(resolved_qty,0) + %s,
                       resolved_at   = CASE
                                         WHEN shortage_qty - %s = 0
                                         THEN CURRENT_TIMESTAMP
                                       END,
                       resolved_by   = %s
                WHERE  shortageid = %s
                """,
                (take, take, take, take, user, r.shortageid),
            )
            remaining -= take

        # remove fully-resolved rows
        self.execute_command("DELETE FROM shelf_shortage WHERE shortage_qty = 0;")

        return remaining
