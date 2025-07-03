# trackpo.py
import streamlit as st
from PO.po_handler import POHandler
from io import BytesIO
import pandas as pd

# Import the new Proposed PO logic
from PO.proposedpo import proposed_po_tab

po_handler = POHandler()

def track_po_tab():
    """Tab for tracking purchase orders (Active vs Proposed)."""
    st.header("🚚 Track Purchase Orders")

    tabs = st.tabs(["📋 Active Orders", "📌 Proposed Adjustments"])

    with tabs[0]:
        # 1) Show active orders: get_all_purchase_orders() 
        #    - excludes completed or any declined from the DB query logic
        po_details = po_handler.get_all_purchase_orders()

        if po_details.empty:
            st.info("ℹ️ No active purchase orders found.")
            return

        # Summarize
        summary_df = po_details[["poid", "suppliername", "status", "expecteddelivery"]].drop_duplicates()
        summary_df.columns = ["PO ID", "Supplier", "Status", "Expected Delivery"]

        st.subheader("📋 **Active Purchase Orders Summary**")
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

        st.subheader("🔍 **Detailed Order Information**")
        selected_poid = st.selectbox(
            "🔽 Select a Purchase Order to view details",
            options=summary_df["PO ID"].tolist()
        )

        selected_order_details = po_details[po_details["poid"] == selected_poid]
        if selected_order_details.empty:
            st.warning("⚠️ No details found for the selected order.")
            return

        order_info = selected_order_details.iloc[0]
        st.write(f"### 📦 Order #{order_info['poid']} – {order_info['suppliername']}")

        col1, col2, col3 = st.columns(3)
        # Order date
        if pd.notnull(order_info['orderdate']):
            col1.metric("🗓️ Order Date", order_info['orderdate'].strftime("%Y-%m-%d"))
        else:
            col1.metric("🗓️ Order Date", "N/A")
        # Expected date
        if pd.notnull(order_info['expecteddelivery']):
            col2.metric("📅 Expected Delivery", order_info['expecteddelivery'].strftime("%Y-%m-%d"))
        else:
            col2.metric("📅 Expected Delivery", "N/A")
        # Status
        col3.metric("🚦 Status", order_info['status'])

        if pd.notnull(order_info['respondedat']):
            st.write(f"**Supplier Response Time:** {order_info['respondedat'].strftime('%Y-%m-%d %H:%M:%S')}")

        st.write("---")
        st.write("#### 📌 **Items in this Order:**")

        for idx, item in selected_order_details.iterrows():
            row_cols = st.columns([1, 4, 2, 2, 2])
            # Show image
            if item['itempicture']:
                image_data = BytesIO(item['itempicture'])
                row_cols[0].image(image_data, width=60)
            else:
                row_cols[0].write("No Image")

            row_cols[1].write(f"**{item['itemnameenglish']}**")
            row_cols[2].write(f"Ordered: {item.get('orderedquantity', 'N/A')}")
            row_cols[3].write(f"Received: {item.get('receivedquantity', 'N/A')}")

            est_price = item.get('estimatedprice', None)
            if pd.notnull(est_price):
                row_cols[4].write(f"Price: ${est_price:.2f}")
            else:
                row_cols[4].write("Price: N/A")

        # Mark delivered
        if order_info['status'] != 'Received':
            st.write("---")
            if st.button("📦 Mark as Delivered & Received"):
                po_handler.update_po_status_to_received(selected_poid)
                st.success(f"✅ Order #{selected_poid} marked as Delivered & Received.")
                st.rerun()
        else:
            st.success("✅ This order has already been marked as Received.")

    with tabs[1]:
        # 2) Proposed Adjustments Tab
        proposed_po_tab(po_handler)
