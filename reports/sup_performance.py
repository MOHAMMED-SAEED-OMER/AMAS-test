import streamlit as st
import pandas as pd
from reports.report_handler import ReportHandler

report_handler = ReportHandler()

def format_delay(hours):
    """Converts hours into a standard format (Days + Hours)."""
    if pd.isna(hours) or hours <= 0:
        return "On Time"  # ✅ Delivered on time
    days = int(hours // 24)
    remaining_hours = int(hours % 24)

    if days > 0 and remaining_hours > 0:
        return f"{days}d {remaining_hours}hr"
    elif days > 0:
        return f"{days}d"
    else:
        return f"{remaining_hours}hr"

def sup_performance_tab():
    """Tab for Supplier Performance Analysis."""
    st.header("📊 Supplier Performance Report")

    # ✅ Fetch supplier performance data
    data = report_handler.get_supplier_performance()

    if data.empty:
        st.warning("⚠️ No supplier performance data available.")
        return

    # ✅ Calculate performance metrics
    data["On-Time Delivery Rate"] = (data["ontimedeliveries"] / data["totalorders"]).fillna(0) * 100
    data["Quantity Accuracy Rate"] = (data["correctquantityorders"] / data["totalorders"]).fillna(0) * 100
    data["Formatted Late Time"] = data["avglatehours"].apply(format_delay)

    # ✅ Format displayed table
    display_data = data[[
        "suppliername",
        "totalorders",
        "ontimedeliveries",
        "latedeliveries",
        "Formatted Late Time",
        "quantitymismatchorders",
        "On-Time Delivery Rate",
        "Quantity Accuracy Rate"
    ]].rename(columns={
        "suppliername": "Supplier",
        "totalorders": "Total Orders",
        "ontimedeliveries": "On-Time Deliveries",
        "latedeliveries": "Late Deliveries",
        "Formatted Late Time": "Avg Late Time",
        "quantitymismatchorders": "Qty Mismatch Orders"
    })

    # ✅ Display summary table
    st.subheader("📋 Supplier Performance Overview")
    st.dataframe(display_data.style.format({
        "On-Time Delivery Rate": "{:.1f}%",
        "Quantity Accuracy Rate": "{:.1f}%"
    }), use_container_width=True)

    # ✅ Highlight underperforming suppliers
    low_performance = data[(data["On-Time Delivery Rate"] < 80) | (data["Quantity Accuracy Rate"] < 80)]
    if not low_performance.empty:
        st.subheader("⚠️ Underperforming Suppliers")
        st.error("These suppliers have low reliability scores:")
        st.dataframe(low_performance[["suppliername", "On-Time Delivery Rate", "Quantity Accuracy Rate"]])

    # ✅ Success Message
    st.success("✅ Report generated successfully!")
