import streamlit as st
from db_handler import DatabaseManager

class ReportHandler(DatabaseManager):
    """Handles fetching report data from the database."""

    def get_supplier_performance(self):
        """Fetch supplier performance data based on PO fulfillment."""
        query = """
        SELECT 
            s.SupplierID,
            s.SupplierName,
            COUNT(po.POID) AS TotalOrders,
            SUM(CASE WHEN po.ActualDelivery <= po.ExpectedDelivery THEN 1 ELSE 0 END) AS OnTimeDeliveries,
            SUM(CASE WHEN po.ActualDelivery > po.ExpectedDelivery THEN 1 ELSE 0 END) AS LateDeliveries,
            AVG(EXTRACT(EPOCH FROM (po.ActualDelivery - po.ExpectedDelivery)) / 3600) AS AvgLateHours,  
            SUM(CASE WHEN poi.ReceivedQuantity = poi.OrderedQuantity THEN 1 ELSE 0 END) AS CorrectQuantityOrders,
            SUM(CASE WHEN poi.ReceivedQuantity <> poi.OrderedQuantity THEN 1 ELSE 0 END) AS QuantityMismatchOrders
        FROM PurchaseOrders po
        JOIN Supplier s ON po.SupplierID = s.SupplierID
        JOIN PurchaseOrderItems poi ON po.POID = poi.POID
        WHERE po.Status = 'Completed'
        GROUP BY s.SupplierID, s.SupplierName
        ORDER BY OnTimeDeliveries DESC;
        """
        return self.fetch_data(query)

    def get_near_expiry_items(self):
        """Fetch items expiring within the next 30 days."""
        query = """
        SELECT 
            i.ItemNameEnglish, 
            inv.Quantity, 
            inv.ExpirationDate, 
            inv.StorageLocation
        FROM Inventory inv
        JOIN Item i ON inv.ItemID = i.ItemID
        WHERE inv.ExpirationDate BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '30 days'
        ORDER BY inv.ExpirationDate ASC;
        """
        return self.fetch_data(query)
