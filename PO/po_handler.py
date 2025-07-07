# PO/po_handler.py  – MySQL backend (all zero-datetime columns sanitized)
import pandas as pd
from datetime import datetime

from db_handler import DatabaseManager


class POHandler(DatabaseManager):
    """Handles all database interactions related to purchase orders (MySQL)."""

    # ───────────────────────── fetch helpers ──────────────────────────
    def _dt_safe(self, col: str) -> str:
        """Return CASE expression that turns 0000-timestamp in `col` to NULL."""
        return (
            f"CASE WHEN {col} = '0000-00-00 00:00:00' "
            f"THEN NULL ELSE {col} END"
        )

    def get_all_purchase_orders(self) -> pd.DataFrame:
        """
        Active & pending POs (everything that is *not* archived).
        All DATETIME/DATE columns are zero-safe.
        """
        query = f"""
            SELECT  po.POID             AS poid,
                    po.SupplierID       AS supplierid,
                    {self._dt_safe('po.OrderDate')}        AS orderdate,
                    {self._dt_safe('po.ExpectedDelivery')} AS expecteddelivery,
                    po.Status           AS status,
                    {self._dt_safe('po.RespondedAt')}      AS respondedat,
                    {self._dt_safe('po.ActualDelivery')}   AS actualdelivery,
                    po.CreatedBy        AS createdby,
                    {self._dt_safe('po.SupProposedDeliver')} AS sup_proposeddeliver,
                    po.SupplierNote     AS suppliernote,
                    po.OriginalPOID     AS originalpoid,
                    s.SupplierName      AS suppliername,

                    poi.ItemID          AS itemid,
                    poi.OrderedQuantity AS orderedquantity,
                    poi.EstimatedPrice  AS estimatedprice,
                    poi.ReceivedQuantity AS receivedquantity,
                    poi.SupProposedQuantity AS supproposedquantity,
                    poi.SupProposedPrice    AS supproposedprice,

                    i.ItemNameEnglish   AS itemnameenglish,
                    i.ItemPicture       AS itempicture
            FROM    purchaseorders      po
            JOIN    supplier            s   ON po.SupplierID = s.SupplierID
            JOIN    purchaseorderitems  poi ON po.POID      = poi.POID
            JOIN    item                i   ON poi.ItemID   = i.ItemID
            WHERE   po.Status NOT IN ('Completed',
                                      'Declined',
                                      'Declined by AMAS',
                                      'Declined by Supplier')
            ORDER BY po.OrderDate DESC
        """
        return self.fetch_data(query)

    def get_archived_purchase_orders(self) -> pd.DataFrame:
        """
        Completed *or* declined POs.
        """
        query = f"""
            SELECT  po.POID             AS poid,
                    po.SupplierID       AS supplierid,
                    {self._dt_safe('po.OrderDate')}        AS orderdate,
                    {self._dt_safe('po.ExpectedDelivery')} AS expecteddelivery,
                    po.Status           AS status,
                    {self._dt_safe('po.RespondedAt')}      AS respondedat,
                    {self._dt_safe('po.ActualDelivery')}   AS actualdelivery,
                    po.CreatedBy        AS createdby,
                    po.SupplierNote     AS suppliernote,
                    s.SupplierName      AS suppliername,

                    poi.ItemID          AS itemid,
                    poi.OrderedQuantity AS orderedquantity,
                    poi.EstimatedPrice  AS estimatedprice,
                    poi.ReceivedQuantity AS receivedquantity,

                    i.ItemNameEnglish   AS itemnameenglish,
                    i.ItemPicture       AS itempicture
            FROM    purchaseorders      po
            JOIN    supplier            s   ON po.SupplierID = s.SupplierID
            JOIN    purchaseorderitems  poi ON po.POID      = poi.POID
            JOIN    item                i   ON poi.ItemID   = i.ItemID
            WHERE   po.Status IN ('Completed',
                                  'Declined',
                                  'Declined by AMAS',
                                  'Declined by Supplier')
            ORDER BY po.OrderDate DESC
        """
        return self.fetch_data(query)

    # ───────────── other fetch helpers (unchanged) ──────────────
    def get_items(self) -> pd.DataFrame:
        return self.fetch_data(
            """
            SELECT  ItemID          AS itemid,
                    ItemNameEnglish AS itemnameenglish,
                    ItemPicture     AS itempicture,
                    AverageRequired AS averagerequired
            FROM    item
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

    # ───────────────────────── write helpers ──────────────────────────
    def create_manual_po(
        self,
        supplier_id: int | None,
        expected_delivery,
        items: list[dict],
        created_by: str,
        original_poid: int | None = None,
    ) -> int | None:
        supplier_id   = int(supplier_id)   if supplier_id   is not None else None
        original_poid = int(original_poid) if original_poid else None

        if pd.notnull(expected_delivery) and not isinstance(expected_delivery, datetime):
            expected_delivery = pd.to_datetime(expected_delivery).to_pydatetime()

        self._ensure_live_conn()
        with self.conn:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO purchaseorders
                        (SupplierID, ExpectedDelivery, CreatedBy, OriginalPOID)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (supplier_id, expected_delivery, created_by, original_poid),
                )
                po_id = cur.lastrowid

                rows = [
                    (
                        po_id,
                        int(it["item_id"]),
                        int(it["quantity"]),
                        it.get("estimated_price"),
                        0,
                    )
                    for it in items
                ]
                cur.executemany(
                    """
                    INSERT INTO purchaseorderitems
                        (POID, ItemID, OrderedQuantity, EstimatedPrice, ReceivedQuantity)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    rows,
                )
        return po_id

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

    # ───────────── proposed-PO workflow (unchanged) ─────────────
    def accept_proposed_po(self, proposed_po_id: int) -> int | None:
        proposed_po_id = int(proposed_po_id)

        po_info_df = self.fetch_data(
            "SELECT * FROM purchaseorders WHERE POID = %s", (proposed_po_id,)
        ).rename(columns=str.lower)

        if po_info_df.empty:
            return None

        po_info   = po_info_df.iloc[0]
        items_df  = self.fetch_data(
            "SELECT * FROM purchaseorderitems WHERE POID = %s", (proposed_po_id,)
        ).rename(columns=str.lower)

        supplier_id = int(po_info["supplierid"]) if pd.notnull(po_info["supplierid"]) else None

        sup_proposed_date = None
        if pd.notnull(po_info.get("supproposeddeliver")) and po_info.get("supproposeddeliver") != '0000-00-00 00:00:00':
            sup_proposed_date = pd.to_datetime(
                po_info["supproposeddeliver"]
            ).to_pydatetime()

        new_items = []
        for _, row in items_df.iterrows():
            qty = (
                int(row["supproposedquantity"])
                if pd.notnull(row.get("supproposedquantity"))
                else int(row.get("orderedquantity") or 1)
            )
            price = (
                float(row["supproposedprice"])
                if pd.notnull(row.get("supproposedprice"))
                else float(row.get("estimatedprice") or 0.0)
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
        new_items: list[dict],
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
