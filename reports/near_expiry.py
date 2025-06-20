import streamlit as st
import pandas as pd
from reports.report_handler import ReportHandler

report_handler = ReportHandler()

def near_expiry_tab():
    """Tab displaying items that are near expiry."""
    st.header("⏳ Items Near Expiry")

    # ✅ Fetch near-expiry items (within 30 days)
    near_expiry_data = report_handler.get_near_expiry_items()

    if near_expiry_data.empty:
        st.success("✅ No items are near expiry!")
        return

    # ✅ Format date for better readability
    near_expiry_data["ExpirationDate"] = pd.to_datetime(near_expiry_data["expirationdate"]).dt.strftime("%Y-%m-%d")

    # ✅ Calculate remaining days
    near_expiry_data["DaysLeft"] = (
        pd.to_datetime(near_expiry_data["expirationdate"]) - pd.Timestamp.today()
    ).dt.days

    # ✅ Select only required columns
    display_data = near_expiry_data[[
        "itemnameenglish",
        "quantity",
        "ExpirationDate",
        "DaysLeft",
        "storagelocation"
    ]].rename(columns={
        "itemnameenglish": "Item",
        "quantity": "Available Quantity",
        "ExpirationDate": "Expiry Date",
        "DaysLeft": "Days Left",
        "storagelocation": "Storage Location"
    })

    # ✅ Highlight critical expiry items (<7 days)
    st.subheader("⚠️ Items Expiring Soon")
    st.dataframe(display_data.style.apply(
        lambda row: ["background-color: #ffcccc" if row["Days Left"] < 7 else "" for _ in row],
        axis=1
    ), use_container_width=True)

    # ✅ Option to export report
    st.download_button(
        label="📥 Download Expiry Report",
        data=display_data.to_csv(index=False),
        file_name="Items_Near_Expiry.csv",
        mime="text/csv"
    )

    st.success("✅ Report generated successfully!")
