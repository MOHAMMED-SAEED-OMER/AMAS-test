# selling_area/shelf_handler.py
"""
Database helpers for the Selling-Area Shelf.
(Stand-alone – no Streamlit imports, no self-import.)
"""
from __future__ import annotations

import pandas as pd

from db_handler import DatabaseManager


class ShelfHandler(DatabaseManager):
    """All DB operations for the ‘shelf’ and related tables."""

    # ─────────────────── current shelf contents ───────────────────
    def get_shelf_items(self) -> pd.DataFrame:
        return self.fetch_data(
            """
            SELECT
                s.shelfid,
                s.itemid,
                i.itemnameenglish AS itemname,
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

    # ─────────────────── most-recent shelf location ───────────────
    def last_locid(self, itemid: int) -> str | None:
        df = self.fetch_data(
            """
            SELECT locid
              FROM shelfentries
             WHERE itemid = %s
               AND locid  IS NOT NULL
          ORDER BY entrydate DESC
             LIMIT 1
            """,
            (itemid,),
        )
        return None if df.empty else str(df.iloc[0, 0])

    # ─────────────────── upsert shelf row (+ log) ─────────────────
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
    ):
        """
        Insert or increment a shelf row; mirror entry in *shelfentries*.
        `locid` is mandatory (column defined NOT NULL).
        """
        own_cur = False
        if cur is None:
            self._ensure_live_conn()
            cur, own_cur = self.conn.cursor(), True

        cur.execute(
            """
            INSERT INTO shelf (itemid, expirationdate, quantity,
                               cost_per_unit, locid)            -- AS new
            VALUES (%s, %s, %s, %s, %s) AS new
            ON DUPLICATE KEY UPDATE
                quantity    = shelf.quantity + new.quantity,
                lastupdated = CURRENT_TIMESTAMP
            """,
            (itemid, expirationdate, quantity, cost_per_unit, locid),
        )

        cur.execute(
            """
            INSERT INTO shelfentries
                   (itemid, expirationdate, quantity, createdby, locid)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (itemid, expirationdate, quantity, created_by, locid),
        )

        if own_cur:
            self.conn.commit()
            cur.close()

    # ─────────────────── inventory helper (barcode) ───────────────
    def get_inventory_by_barcode(self, barcode: str) -> pd.DataFrame:
        return self.fetch_data(
            """
            SELECT
                inv.itemid,
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

    # ─────────────────── shortage resolver (transfer) ─────────────
    def resolve_shortages(self, *, itemid: int, qty_need: int, user: str) -> int:
        rows = self.fetch_data(
            """
            SELECT shortageid, shortage_qty
              FROM shelf_shortage
             WHERE itemid  = %s
               AND resolved = FALSE
          ORDER BY logged_at
            """,
            (itemid,),
        )

        remaining = qty_need
        for r in rows.itertuples():
            if remaining == 0:
                break
            take = min(remaining, int(r.shortage_qty))
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
                 WHERE shortageid   = %s
                """,
                (take, take, take, take, user, r.shortageid),
            )
            remaining -= take

        # remove fully-zero rows
        self.execute_command("DELETE FROM shelf_shortage WHERE shortage_qty = 0;")
        return remaining

    # ─────────────────── low-stock quick query ────────────────────
    def get_low_shelf_stock(self, threshold: int = 10) -> pd.DataFrame:
        return self.fetch_data(
            """
            SELECT
                s.itemid,
                i.itemnameenglish AS itemname,
                s.quantity,
                s.expirationdate
              FROM shelf s
              JOIN item  i ON s.itemid = i.itemid
             WHERE s.quantity <= %s
          ORDER BY s.quantity ASC
            """,
            (threshold,),
        )

    # ─────────────────── master item list (manage tab) ────────────
    def get_all_items(self) -> pd.DataFrame:
        df = self.fetch_data(
            """
            SELECT
                itemid,
                itemnameenglish AS itemname,
                shelfthreshold,
                shelfaverage
              FROM item
          ORDER BY itemnameenglish
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
               SET shelfthreshold = %s,
                   shelfaverage   = %s
             WHERE itemid = %s
            """,
            (int(thr), int(avg), int(itemid)),
        )

    # ─────────────────── quantity-by-item (alerts tab) ────────────
    def get_shelf_quantity_by_item(self) -> pd.DataFrame:
        df = self.fetch_data(
            """
            SELECT
                i.itemid,
                i.itemnameenglish AS itemname,
                COALESCE(SUM(s.quantity),0) AS totalquantity,
                i.shelfthreshold,
                i.shelfaverage
              FROM item  i
         LEFT JOIN shelf s ON i.itemid = s.itemid
          GROUP BY i.itemid, i.itemnameenglish,
                   i.shelfthreshold, i.shelfaverage
          ORDER BY i.itemnameenglish
            """
        )
        if not df.empty:
            df["shelfthreshold"] = df["shelfthreshold"].astype("Int64")
            df["shelfaverage"]   = df["shelfaverage"].astype("Int64")
            df["totalquantity"]  = df["totalquantity"].astype(int)
        return df
