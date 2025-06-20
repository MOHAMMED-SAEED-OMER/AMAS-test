import streamlit as st
import pandas as pd 
from PO.po_handler import POHandler
from io import BytesIO

po_handler = POHandler()

def archived_po_tab():
    """Tab displaying archived (completed and declined) purchase orders."""
    st.header("📦 Archived Purchase Orders")

    # Fetch all archived purchase orders
    archived_orders = po_handler.get_archived_purchase_orders()

    if archived_orders.empty:
        st.info("ℹ️ No archived purchase orders found.")
        return

    # Correctly separate Completed and Declined orders
    completed_orders = archived_orders[archived_orders["status"] == "Completed"]
    declined_orders = archived_orders[
        archived_orders["status"].isin(["Declined", "Declined by AMAS", "Declined by Supplier"])
    ]

    # Section: Completed Orders
    st.subheader("✅ Completed Orders")
    if not completed_orders.empty:
        for poid, group in completed_orders.groupby("poid"):
            order_info = group.iloc[0]
            with st.expander(f"📦 PO #{poid} - {order_info['suppliername']}"):
                st.write(f"**Order Date:** {order_info['orderdate'].strftime('%Y-%m-%d')}")

                actual_delivery = order_info.get("actualdelivery")
                if pd.notnull(actual_delivery):
                    st.write(f"**Delivered on:** {actual_delivery.strftime('%Y-%m-%d')}")
                else:
                    st.write("**Delivered on:** Not Recorded")

                for idx, item in group.iterrows():
                    cols = st.columns([1, 3, 2])
                    if item['itempicture']:
                        cols[0].image(BytesIO(item['itempicture']), width=50)
                    else:
                        cols[0].write("No Image")
                    cols[1].write(f"{item['itemnameenglish']}")
                    cols[2].write(f"Received: {item['receivedquantity']}")
    else:
        st.info("No completed orders available.")

    # Section: Declined Orders (covers all decline types)
    st.subheader("❌ Declined Orders")
    if not declined_orders.empty:
        for poid, group in declined_orders.groupby("poid"):
            order_info = group.iloc[0]
            status = order_info['status']
            with st.expander(f"📦 PO #{poid} - {order_info['suppliername']} ({status})"):
                st.write(f"**Order Date:** {order_info['orderdate'].strftime('%Y-%m-%d')}")

                responded_at = order_info.get("respondedat")
                if pd.notnull(responded_at):
                    st.write(f"**Declined on:** {responded_at.strftime('%Y-%m-%d')}")
                else:
                    st.write("**Declined on:** Not Recorded")

                supplier_note = order_info.get("suppliernote", "No note provided")
                st.write(f"**Supplier Note:** {supplier_note}")

                for idx, item in group.iterrows():
                    cols = st.columns([1, 3, 2])
                    if item['itempicture']:
                        cols[0].image(BytesIO(item['itempicture']), width=50)
                    else:
                        cols[0].write("No Image")
                    cols[1].write(f"{item['itemnameenglish']}")
                    cols[2].write(f"Ordered: {item['orderedquantity']}")
    else:
        st.info("No declined orders available.")
