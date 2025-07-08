# selling_area/shelf_handler.py
import pandas as pd
from db_handler import DatabaseManager


class ShelfHandler(DatabaseManager):
    """Handles database operations related to the Shelf (Selling Area)."""

    # ───────── recent shelf location ───────────────────────────────
    def last_locid(self, itemid: int) -> str | None:
        df = self.fetch_data(
            """
            SELECT locid
            FROM   shelfentries
            WHERE  itemid = %s AND locid IS NOT NULL
            ORDER  BY entrydate DESC
            LIMIT 1
            """,
            (itemid,),
        )
        return None if df.empty else str(df.iloc[0, 0])

    # ───────── upsert into shelf (+log) ────────────────────────────
    def add_to_shelf(
        self,
        *,
        itemid: int,
        expirationdate,
        quantity: int,
        created_by: str,
        cost_per_unit: float,
        locid: str | None,
        cur=None,            # optional open cursor for transactions
    ):
        """
        Insert–or–increment a shelf row and write a shelfentries log.
        `locid` is mandatory for NOT-NULL schema.
        """
        own = False
        if cur is None:
            self._ensure_live_conn()
            cur = self.conn.cursor()
            own = True

        itemid = int(itemid)
        qty    = int(quantity)
        cost   = float(cost_per_unit)

        # 1️⃣ upsert shelf row (UNIQUE must cover itemid, expirationdate, cost_per_unit)
        cur.execute(
            """
            INSERT INTO shelf (itemid, expirationdate, quantity, cost_per_unit, locid)
            VALUES (%s, %s, %s, %s, %s) AS new
            ON DUPLICATE KEY UPDATE
                quantity    = shelf.quantity + new.quantity,
                lastupdated = CURRENT_TIMESTAMP
            """,
            (itemid, expirationdate, qty, cost, locid),
        )

        # 2️⃣ movement log
        cur.execute(
            """
            INSERT INTO shelfentries (itemid, expirationdate, quantity, createdby, locid)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (itemid, expirationdate, qty, created_by, locid),
        )

        if own:
            self.conn.commit()
            cur.close()

    # --------------- rest of the class unchanged ------------------
    # (get_shelf_items, transfer_from_inventory, alerts helpers, shortage resolver, ...)
