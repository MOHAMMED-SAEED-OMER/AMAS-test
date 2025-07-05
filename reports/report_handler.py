# reports/report_handler.py  – MySQL edition
from db_handler import DatabaseManager


class ReportHandler(DatabaseManager):
    """Report-level data helpers (now MySQL syntax)."""

    # ───────────────────────── Supplier Performance ─────────────────────────
    def get_supplier_performance(self):
        """
        PO fulfilment KPIs per supplier.
        • AvgLateHours uses TIMESTAMPDIFF instead of Postgres EXTRACT.
        """
        query = """
            SELECT
                s.supplierid,
                s.suppliername,
                COUNT(po.poid) AS TotalOrders,

                SUM(CASE
                        WHEN po.actualdelivery <= po.expecteddelivery
                        THEN 1 ELSE 0
                    END) AS OnTimeDeliveries,

                SUM(CASE
                        WHEN po.actualdelivery > po.expecteddelivery
                        THEN 1 ELSE 0
                    END) AS LateDeliveries,

                AVG(
                    TIMESTAMPDIFF(
                        HOUR,
                        po.expecteddelivery,
                        po.actualdelivery
                    )
                ) AS AvgLateHours,

                SUM(CASE
                        WHEN poi.receivedquantity = poi.orderedquantity
                        THEN 1 ELSE 0
                    END) AS CorrectQuantityOrders,

                SUM(CASE
                        WHEN poi.receivedquantity <> poi.orderedquantity
                        THEN 1 ELSE 0
                    END) AS QuantityMismatchOrders

            FROM   purchaseorders      po
            JOIN   supplier            s   ON s.supplierid = po.supplierid
            JOIN   purchaseorderitems  poi ON poi.poid      = po.poid
            WHERE  po.status = 'Completed'
            GROUP  BY s.supplierid, s.suppliername
            ORDER  BY OnTimeDeliveries DESC;
        """
        return self.fetch_data(query)

    # ───────────────────────── Near-Expiry Stock ────────────────────────────
    def get_near_expiry_items(self):
        """
        Items whose expiration date is within the next 30 days.
        Replaces Postgres ‘+ INTERVAL '30 days'’ with MySQL DATE_ADD.
        """
        query = """
            SELECT
                i.itemnameenglish,
                inv.quantity,
                inv.expirationdate,
                inv.storagelocation
            FROM   inventory  inv
            JOIN   item       i ON i.itemid = inv.itemid
            WHERE  inv.expirationdate BETWEEN CURDATE()
                                         AND DATE_ADD(CURDATE(), INTERVAL 30 DAY)
            ORDER  BY inv.expirationdate ASC;
        """
        return self.fetch_data(query)
