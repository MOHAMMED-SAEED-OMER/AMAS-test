# PO/manualpo.py
import datetime
from zoneinfo import ZoneInfo

import streamlit as st
from PO.po_handler import POHandler

po_handler = POHandler()
BAGHDAD_TZ = ZoneInfo("Asia/Baghdad")      # use built-in zoneinfo (Python 3.9+)


def manual_po_tab() -> None:
    st.header("📝 Create Manual Purchase Order")

    # ── login guard ───────────────────────────────────────────
    if "user_email" not in st.session_state:
        st.info("🔒 Please sign in to create a purchase order.")
        return
    user_email: str = st.session_state["user_email"]

    # ── one-time feedback from previous run ──────────────────
    if "po_feedback" in st.session_state:
        st.success(st.session_state.pop("po_feedback"))

    # ── load reference data ──────────────────────────────────
    suppliers_df     = po_handler.get_suppliers()
    items_df         = po_handler.get_items()
    item_supplier_df = po_handler.get_item_supplier_mapping()

    if suppliers_df.empty or items_df.empty or item_supplier_df.empty:
        st.warning("⚠️ No suppliers or items available.")
        return

    # ── supplier selector ────────────────────────────────────
    sup_opts        = suppliers_df.set_index("suppliername")["supplierid"].to_dict()
    sel_sup_name    = st.selectbox("🏢 Select Supplier", list(sup_opts.keys()))
    sel_sup_id: int = sup_opts[sel_sup_name]

    # items supplied by the chosen supplier
    supplier_items = item_supplier_df[item_supplier_df["supplierid"] == sel_sup_id]["itemid"]
    filt_items_df  = items_df[items_df["itemid"].isin(supplier_items)]

    if filt_items_df.empty:
        st.warning("⚠️ No items available for this supplier.")
        return

    # ── expected delivery datetime ───────────────────────────
    st.write("### 📅 Expected Delivery Date and Time")
    c_date, c_time = st.columns(2)
    d_date = c_date.date_input(
        "Select Date",
        min_value=datetime.date.today(),
        value=datetime.date.today()
    )
    d_time = c_time.time_input("Select Time", value=datetime.time(9, 0))

    expected_dt = (
        datetime.datetime.combine(d_date, d_time)
        .replace(tzinfo=BAGHDAD_TZ)                # attach Baghdad TZ
    )

    # ── item multiselect ─────────────────────────────────────
    item_opts       = filt_items_df.set_index("itemnameenglish")["itemid"].to_dict()
    sel_item_names  = st.multiselect(
        "🏷️ Items to include",
        list(item_opts.keys()),
        key="po_item_multiselect",
    )

    # ── qty / price entry form ───────────────────────────────
    po_items: list[dict] = []
    if sel_item_names:
        with st.form("po_item_form", clear_on_submit=True):
            st.write("### ✏️ Enter Quantity & Estimated Price")

            for name in sel_item_names:
                iid = item_opts[name]
                st.write(f"**{name}**")
                qcol, pcol = st.columns(2)

                qty = qcol.number_input(
                    f"Qty ({name})",
                    min_value=1,
                    step=1,
                    key=f"qty_{iid}",
                )
                price = pcol.number_input(
                    f"Est. Price ({name})",
                    min_value=0.01,           # must be >0 to avoid NULL/0 issues
                    step=0.01,
                    key=f"price_{iid}",
                )
                po_items.append(
                    {
                        "item_id": iid,
                        "quantity": qty,
                        "estimated_price": price,
                    }
                )

            submitted = st.form_submit_button("📤 Submit Purchase Order")

        # ── handle submission outside the form ───────────────
        if submitted:
            if not po_items:
                st.error("❌ Please select at least one item.")
                st.stop()

            try:
                # keyword args protect against future signature changes
                poid = po_handler.create_manual_po(
                    supplier_id=sel_sup_id,
                    expected_delivery=expected_dt,
                    items=po_items,
                    created_by=user_email,
                )
            except Exception as exc:
                # expose underlying DB / validation error while developing
                st.exception(exc)
                st.stop()

            msg = (
                f"✅ Purchase Order #{poid} created successfully by {user_email}!"
                if poid
                else "❌ Failed to create purchase order. Please try again."
            )

            # store feedback & reset multiselect to clear UI in next run
            st.session_state["po_feedback"] = msg
            st.session_state.pop("po_item_multiselect", None)
            st.rerun()


# Stand-alone test
if __name__ == "__main__":
    manual_po_tab()
