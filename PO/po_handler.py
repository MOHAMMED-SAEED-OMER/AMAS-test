# PO/po_handler.py  – MySQL backend (full version patched 2025-07-07)
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, List, Dict

import pandas as pd
import mysql.connector
from mysql.connector import Error as MySQLError
from mysql.connector.cursor_cext import CMySQLCursorDict

from db_handler import DatabaseManager


logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.INFO)


class POHandler(DatabaseManager):
    """All DB interactions for Purchase Orders (MySQL)."""

    # ───────────────────────── helpers ─────────────────────────
    @staticmethod
    def _dt_safe(col: str) -> str:
        """Replace legacy zero-dates with NULL so they cast cleanly."""
        return f"CASE WHEN {col} = '0000-00-00 00:00:00' THEN NULL ELSE {col} END"

    def _patch_sql_mode(self) -> None:
        """
        Strip the three deprecated flags that raise MySQL-8 warning 3135.
        If that warning is still thrown, swallow it once.
        """
        try:
            self.execute_command(
                """
                SET SESSION sql_mode = (
                    SELECT REPLACE(
                             REPLACE(
                               REPLACE(@@SESSION.sql_mode,
                                       'NO_ZERO_DATE',''),
                               'NO_ZERO_IN_DATE',''),
                             'ERROR_FOR_DIVISION_BY_ZERO','')
                )
                """
            )
        except mysql.connector.Error as err:
            if err.errno != 3135:           # any *other* error → re-raise
                raise

    # ───────────────────── reference look-ups ─────────────────────
    def get_items(self) -> pd.DataFrame:
        return self.fetch_data(
            """
            SELECT  ItemID AS itemid,
                    ItemNameEnglish AS itemnameenglish,
                    ItemPicture AS itempicture,
                    AverageRequired AS averagerequired
            FROM item
            """
        )

    def get_item_supplier_mapping(self) -> pd.DataFrame:
        return self.fetch_data(
            "SELECT ItemID AS itemid, SupplierID AS supplierid FROM itemsupplier"
        )

    def get_suppliers(self) -> pd.DataFrame:
        return self.fetch_data(
            "SELECT SupplierID AS supplierid, SupplierName AS suppliername FROM supplier"
        )

    # ───────────────────── active / pending POs ─────────────────────
    def get_all_purchase_orders(self) -> pd.DataFrame:
        self._patch_sql_mode()
        safe_orderdate = self._dt_safe("po.OrderDate")

        query = f"""
            SELECT  po.POID   AS poid,
                    po.SupplierID AS supplierid,
                    {safe_orderdate} AS orderdate,
                    {self._dt_safe('po.ExpectedDelivery')} AS expecteddelivery,
                    po.Status AS status,
                    {self._dt_safe('po.RespondedAt')}  AS respondedat,
                    {self._dt_safe('po.ActualDelivery')} AS actualdelivery,
                    po.CreatedBy AS createdby,
                    {self._dt_safe('po.SupProposedDeliver')} AS sup_proposeddeliver,
                    po.SupplierNote AS suppliernote,
                    po.OriginalPOID AS originalpoid,
                    s.SupplierName AS suppliername,

                    poi.ItemID AS itemid,
                    poi.OrderedQuantity AS orderedquantity,
                    poi.EstimatedPrice AS estimatedprice,
                    poi.ReceivedQuantity AS receivedquantity,
                    poi.SupProposedQuantity AS supproposedquantity,
                    poi.SupProposedPrice AS supproposedprice,

                    i.ItemNameEnglish AS itemnameenglish,
                    i.ItemPicture AS itempicture
            FROM    purchaseorders      po
            JOIN    supplier            s   ON po.SupplierID = s.SupplierID
            JOIN    purchaseorderitems  poi ON po.POID      = poi.POID
            JOIN    item                i   ON poi.ItemID   = i.ItemID
            WHERE   po.Status NOT IN ('Completed',
                                      'Declined',
                                      'Declined by AMAS',
                                      'Declined by Supplier')
            ORDER BY {safe_orderdate} DESC
        """
        return self.fetch_data(query)

    # ─── archived (completed / declined) POs ───
    def get_archived_purchase_orders(self) -> pd.DataFrame:
        self._patch_sql_mode()
        safe_orderdate = self._dt_safe("po.OrderDate")

        query = f"""
            SELECT  po.POID   AS poid,
                    po.SupplierID AS supplierid,
                    {safe_orderdate} AS orderdate,
                    {self._dt_safe('po.ExpectedDelivery')} AS expecteddelivery,
                    po.Status AS status,
                    {self._dt_safe('po.RespondedAt')}  AS respondedat,
                    {self._dt_safe('po.ActualDelivery')} AS actualdelivery,
                    po.CreatedBy AS createdby,
                    po.SupplierNote AS suppliernote,
                    s.SupplierName AS suppliername,

                    poi.ItemID AS itemid,
                    poi.OrderedQuantity AS orderedquantity,
                    poi.EstimatedPrice AS estimatedprice,
                    poi.ReceivedQuantity AS receivedquantity,

                    i.ItemNameEnglish AS itemnameenglish,
                    i.ItemPicture AS itempicture
            FROM    purchaseorders      po
            JOIN    supplier            s   ON po.SupplierID = s.SupplierID
            JOIN    purchaseorderitems  poi ON po.POID      = poi.POID
            JOIN    item                i   ON poi.ItemID   = i.ItemID
            WHERE   po.Status IN ('Completed',
                                  'Declined',
                                  'Declined by AMAS',
                                  'Declined by Supplier')
            ORDER BY {safe_orderdate} DESC
        """
        return self.fetch_data(query)

    # ───────────────────── PO creation (patched) ─────────────────────
    def create_manual_po(
        self,
        supplier_id: int | None,
        expected_delivery,
        items: List[Dict[str, Any]],
        created_by: str,
        original_poid: int | None = None,
    ) -> int | None:
        """
        Insert a PO header and its lines.
        Returns the new POID or None on failure.
        """

        # ---- quick checks ------------------------------------------------
        if not items:
            logger.warning("create_manual_po called with empty items list")
            return None

        supplier_id   = int(supplier_id)   if supplier_id is not None else None
        original_poid = int(original_poid) if original_poid else None

        if pd.notnull(expected_delivery) and not isinstance(expected_delivery, datetime):
            expected_delivery = pd.to_datetime(expected_delivery).to_pydatetime()

        # MySQL can't store tz-aware datetimes
        if expected_delivery is not None and expected_delivery.tzinfo is not None:
            expected_delivery = expected_delivery.replace(tzinfo=None)

        # ensure price never NULL / 0 if column is NOT NULL
        for it in items:
            if it.get("estimated_price") in (None, 0, 0.0):
                it["estimated_price"] = 0.00

        self._ensure_live_conn()
        self._patch_sql_mode()

        try:
            with self.conn:
                with self.conn.cursor(dictionary=True) as cur:  # type: CMySQLCursorDict
                    # ---------- header ------------------------------------
                    cur.execute(
                        """
                        INSERT INTO purchaseorders
                            (SupplierID, ExpectedDelivery,
                             Status, CreatedBy, OrderDate, OriginalPOID)
                        VALUES (%s, %s, 'Pending', %s, NOW(), %s)
                        """,
                        (supplier_id, expected_delivery, created_by, original_poid),
                    )
                    poid = cur.lastrowid

                    # ---------- lines -------------------------------------
                    rows = [
                        (
                            poid,
                            int(it["item_id"]),
                            int(it["quantity"]),
                            float(it["estimated_price"]),
                            0,  # ReceivedQuantity
                        )
                        for it in items
                    ]
                    cur.executemany(
                        """
                        INSERT INTO purchaseorderitems
                            (POID, ItemID, OrderedQuantity,
                             EstimatedPrice, ReceivedQuantity)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        rows,
                    )

            logger.info("Manual PO %s created by %s (%d lines)", poid, created_by, len(items))
            return poid

        except MySQLError as exc:
            logger.exception("MySQL error while creating PO: %s", exc)
            return None
        except Exception as exc:
            logger.exception("Unexpected error while creating PO: %s", exc)
            return None

    # ───────────────────── updates & workflows ─────────────────────
    def update_po_status_to_received(self, poid: int) -> None:
        self.execute_command(
            """
            UPDATE purchaseorders
               SET Status = 'Received',
                   ActualDelivery = CURRENT_TIMESTAMP
             WHERE POID = %s
            """,
            (int(poid),),
        )

    def update_received_quantity(
        self, poid: int, item_id: int, received_quantity: int
    ) -> None:
        self.execute_command(
            """
            UPDATE purchaseorderitems
               SET ReceivedQuantity = %s
             WHERE POID = %s AND ItemID = %s
            """,
            (int(received_quantity), int(poid), int(item_id)),
        )

    # ───── proposed-PO workflow (accept / decline / modify) ─────
    def accept_proposed_po(self, proposed_po_id: int) -> int | None:
        proposed_po_id = int(proposed_po_id)

        po_info_df = self.fetch_data(
            "SELECT * FROM purchaseorders WHERE POID = %s", (proposed_po_id,)
        ).rename(columns=str.lower)
        if po_info_df.empty:
            return None
        po_info = po_info_df.iloc[0]

        items_df = self.fetch_data(
            "SELECT * FROM purchaseorderitems WHERE POID = %s", (proposed_po_id,)
        ).rename(columns=str.lower)

        supplier_id = int(po_info["supplierid"]) if pd.notnull(po_info["supplierid"]) else None

        sup_proposed_date = None
        if pd.notnull(po_info.get("supproposeddeliver")) and po_info.get(
            "supproposeddeliver"
        ) != "0000-00-00 00:00:00":
            sup_proposed_date = pd.to_datetime(po_info["supproposeddeliver"]).to_pydatetime()

        new_items = []
        for _, row in items_df.iterrows():
            qty = int(
                row["supproposedquantity"]
                if pd.notnull(row.get("supproposedquantity"))
                else row.get("orderedquantity") or 1
            )
            price = float(
                row["supproposedprice"]
                if pd.notnull(row.get("supproposedprice"))
                else row.get("estimatedprice") or 0.0
            )
            new_items.append(
                {"item_id": int(row["itemid"]), "quantity": qty, "estimated_price": price}
            )

        created_by = po_info.get("createdby", "Unknown")

        new_poid = self.create_manual_po(
            supplier_id=supplier_id,
            expected_delivery=sup_proposed_date,
            items=new_items,
            created_by=created_by,
            original_poid=proposed_po_id,
        )

        self.execute_command(
            "UPDATE purchaseorders SET Status = 'Accepted by AMAS' WHERE POID = %s",
            (proposed_po_id,),
        )
        return new_poid

    def decline_proposed_po(self, proposed_po_id: int) -> None:
        self.execute_command(
            "UPDATE purchaseorders SET Status = 'Declined by AMAS' WHERE POID = %s",
            (int(proposed_po_id),),
        )

    def modify_proposed_po(
        self,
        proposed_po_id: int,
        new_delivery_date,
        new_items: List[Dict[str, Any]],
        user_email: str,
    ) -> int | None:
        proposed_po_id = int(proposed_po_id)

        po_info_df = self.fetch_data(
            "SELECT * FROM purchaseorders WHERE POID = %s", (proposed_po_id,)
        )
        if po_info_df.empty:
            return None
        po_info = po_info_df.iloc[0]

        supplier_id = int(po_info["supplierid"]) if pd.notnull(po_info["supplierid"]) else None

        new_poid = self.create_manual_po(
            supplier_id=supplier_id,
            expected_delivery=new_delivery_date,
            items=new_items,
            created_by=user_email,
            original_poid=proposed_po_id,
        )

        self.execute_command(
            "UPDATE purchaseorders SET Status = 'Modified by AMAS' WHERE POID = %s",
            (proposed_po_id,),
        )
        return new_poid
