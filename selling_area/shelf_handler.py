# selling_area/shelf_handler.py
#
# DB helper class for everything that happens in the Selling-Area “Shelf”.
# Fully self-contained; safe for MySQL 8.0 (no deprecated VALUES() calls).

from __future__ import annotations

import pandas as pd
from db_handler import DatabaseManager


class ShelfHandler(DatabaseManager):
    """All database helpers for the Selling-Area shelf."""

    # ────────────────────────────────────────────────────────────────
    # 1.  Current shelf contents
    # ────────────────────────────────────────────────────────────────
    def get_shelf_items(self) -> pd.DataFrame:
        return self.fetch_data(
            """
            SELECT s.shelfid,
                   s.itemid,
                   i.itemnameenglish        AS itemname,
                   s.quantity,
                   s.expirationdate,
                   s.cost_per_unit,
                   s.locid,
                   s.lastupdated
            FROM   shelf s
            JOIN   item  i ON s.itemid = i.itemid
            ORDER  BY i.itemnameenglish, s.expirationdate
            """
        )

    # ────────────────────────────────────────────────────────────────
    # 2.  Last used shelf location for an item (nice UX helper)
    # ────────────────────────────────────────────────────────────────
    def last_locid(self, itemid: int) -> str | None:
        df = self.fetch_data(
            """
            SELECT locid
            FROM   shelfentries
            WHERE  itemid = %s
              AND  locid IS NOT NULL
            ORDER  BY entrydate DESC
            LIMIT 1
            """,
            (itemid,),
        )
        return None if df.empty else str(df.iloc[0, 0])

    # ────────────────────────────────────────────────────────────────
    # 3.  Insert / increment shelf row  +  movement log
    #     (locid is NOT-NULL in schema → always required)
    # ────────────────────────────────────────────────────────────────
    def add_to_shelf(
        self,
        *,
        itemid: int,
        expirationdate,
        quantity: int,
        created_by: str,
        cost_per_unit: float,
        locid: str,
        cur=None,
    ) -> None:
        """
        Upsert a shelf row (unique on item + expiry + cost) **and**
        write to `shelfentries`.

        • Uses `… VALUES (…) AS new` then `new.column` – compliant with
          MySQL 8.0 (avoids deprecated VALUES(col) syntax).
        • If *cur* is supplied we reuse it (so a calling transaction can
          include inventory decrement, etc.); otherwise we open our own
          cursor/commit for simplicity.
        """
        qty  = int(quantity)
        cost = float(cost_per_unit)

        own = False
        if cur is None:
            self._ensure_live_conn()
            cur, own = self.conn.cursor(), True

        # 1️⃣  Upsert shelf row
        cur.execute(
            """
            INSERT INTO shelf (itemid, expirationdate, quantity,
                               cost_per_unit, locid)
            VALUES (%s, %s, %s, %s, %s) AS new
            ON DUPLICATE KEY UPDATE
                quantity     = shelf.quantity + new.quantity,
                cost_per_unit= new.cost_per_unit,
                locid        = new.locid,
                lastupdated  = CURRENT_TIMESTAMP
            """,
            (itemid, expirationdate, qty, cost, locid),
        )

        # 2️⃣  Movement log ─ every NOT-NULL column supplied
        cur.execute(
            """
            INSERT INTO shelfentries
                   (itemid, expirationdate, quantity,
                    cost_per_unit, createdby, locid)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (itemid, expirationdate, qty, cost, created_by, locid),
        )

        if own:
            self.conn.commit()
            cur.close()

    # ────────────────────────────────────────────────────────────────
    # 4.  Inventory helper (barcode-lookup for Transfer tab)
    # ────────────────────────────────────────────────────────────────
    def get_inventory_by_barcode(self, barcode: str) -> pd.DataFrame:
        return self.fetch_data(
            """
            SELECT inv.itemid,
                   i.itemnameenglish AS itemname,
                   inv.quantity,
                   inv.expirationdate,
                   inv.cost_per_unit
            FROM   inventory inv
            JOIN   item       i ON inv.itemid = i.itemid
            WHERE  i.barcode = %s
              AND  inv.quantity > 0
            ORDER  BY inv.expirationdate
            """,
            (barcode,),
        )

    # ────────────────────────────────────────────────────────────────
    # 5.  Shortage resolver  (used by Transfer.confirm)
    # ────────────────────────────────────────────────────────────────
    def resolve_shortages(self, *, itemid: int, qty_need: int, user: str) -> int:
        """
        Consume the oldest open shortages for *itemid* up to *qty_need*.
        Returns how many units still need to be placed on shelf afterwards.
        """
        rows = self.fetch_data(
            """
            SELECT shortageid, shortage_qty
            FROM   shelf_shortage
            WHERE  itemid = %s
              AND  resolved = FALSE
            ORDER  BY logged_at
            """,
            (itemid,),
        )

        remaining = qty_need
        for r in rows.itertuples():
            if remaining == 0:
                break
            take = min(remaining, int(r.shortage_qty))

            # shrink / resolve the shortage row
            self.execute_command(
                """
                UPDATE shelf_shortage
                SET shortage_qty = shortage_qty - %s,
                    resolved      = (shortage_qty - %s = 0),
                    resolved_qty  = COALESCE(resolved_qty,0) + %s,
                    resolved_at   = CASE
                                       WHEN shortage_qty - %s = 0
                                       THEN CURRENT_TIMESTAMP
                                    END,
                    resolved_by   = %s
                WHERE shortageid = %s
                """,
                (take, take, take, take, user, r.shortageid),
            )
            remaining -= take

        # tidy up zero-quantity rows
        self.execute_command("DELETE FROM shelf_shortage WHERE shortage_qty = 0;")
        return remaining

    # ────────────────────────────────────────────────────────────────
    # 6.  Quick low-stock query for Alerts tab
    # ────────────────────────────────────────────────────────────────
    def get_low_shelf_stock(self, threshold: int = 10) -> pd.DataFrame:
        return self.fetch_data(
            """
            SELECT s.itemid,
                   i.itemnameenglish AS itemname,
                   s.quantity,
                   s.expirationdate
            FROM   shelf s
            JOIN   item  i ON s.itemid = i.itemid
            WHERE  s.quantity <= %s
            ORDER  BY s.quantity ASC
            """,
            (threshold,),
        )

    # ────────────────────────────────────────────────────────────────
    # 7.  Master item list (Manage-Settings tab)
    # ────────────────────────────────────────────────────────────────
    def get_all_items(self) -> pd.DataFrame:
        df = self.fetch_data(
            """
            SELECT itemid,
                   itemnameenglish AS itemname,
                   shelfthreshold,
                   shelfaverage
            FROM   item
            ORDER  BY itemnameenglish
            """
        )
        if not df.empty:
            df["shelfthreshold"] = df["shelfthreshold"].astype("Int64")
            df["shelfaverage"]   = df["shelfaverage"].astype("Int64")
        return df

    def update_shelf_settings(self, itemid: int, thr: int, avg: int) -> None:
        self.execute_command(
            """
            UPDATE item
            SET    shelfthreshold = %s,
                   shelfaverage   = %s
            WHERE  itemid = %s
            """,
            (int(thr), int(avg), int(itemid)),
        )

    # ────────────────────────────────────────────────────────────────
    # 8.  Quantity-by-item (Alerts tab)
    # ────────────────────────────────────────────────────────────────
    def get_shelf_quantity_by_item(self) -> pd.DataFrame:
        df = self.fetch_data(
            """
            SELECT i.itemid,
                   i.itemnameenglish AS itemname,
                   COALESCE(SUM(s.quantity), 0) AS totalquantity,
                   i.shelfthreshold,
                   i.shelfaverage
            FROM   item  i
            LEFT JOIN shelf s ON i.itemid = s.itemid
            GROUP  BY i.itemid, i.itemnameenglish,
                     i.shelfthreshold, i.shelfaverage
            ORDER  BY i.itemnameenglish
            """
        )
        if not df.empty:
            df["totalquantity"]  = df["totalquantity"].astype(int)
            df["shelfthreshold"] = df["shelfthreshold"].astype("Int64")
            df["shelfaverage"]   = df["shelfaverage"].astype("Int64")
        return df
