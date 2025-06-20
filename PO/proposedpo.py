# PO/proposedpo.py
import streamlit as st
import pandas as pd
from datetime import date, datetime, time


# ───────────────────────── helpers ─────────────────────────
def _fmt(val, is_changed, prefix=""):
    """Return Markdown string with green (✓) or red (✗) colour."""
    colour = "#d9534f" if is_changed else "#5cb85c"   # red / green
    return f"<span style='color:{colour};font-weight:bold;'>{prefix}{val}</span>"


def _same(a, b) -> bool:
    """Treat NaNs as None, then compare"""
    a = None if pd.isnull(a) else a
    b = None if pd.isnull(b) else b
    return a == b


# ───────────────────────── main tab ─────────────────────────
def proposed_po_tab(po_handler):
    st.subheader("📌 **Supplier Proposed Adjustments**")

    all_po = po_handler.get_all_purchase_orders()
    proposed_po_df = all_po[all_po["status"] == "Proposed by Supplier"]

    if proposed_po_df.empty:
        st.success("✅ No supplier proposals awaiting review.")
        return

    for poid in proposed_po_df["poid"].unique():
        po_data = proposed_po_df[proposed_po_df["poid"] == poid]
        po_info = po_data.iloc[0]

        st.markdown(f"## 📝 PO #{poid} from {po_info['suppliername']}")

        # -------- supplier note ----------
        sup_note = po_info.get("suppliernote") or "No note provided"
        st.markdown(f"**Supplier Note:** {sup_note}")

               # ----- Delivery date & time ------------------------------------
        sup_raw   = po_info.get("sup_proposeddeliver")
        orig_raw  = po_info.get("expecteddelivery")

        if pd.notnull(sup_raw):
            sup_dt  = pd.to_datetime(sup_raw)
            orig_dt = pd.to_datetime(orig_raw) if pd.notnull(orig_raw) else None

            same_dt = _same(orig_dt, sup_dt)

            fmt = lambda dt: dt.strftime("%Y‑%m‑%d %H:%M") if dt else "N/A"
            st.markdown(
                "Delivery: "
                + _fmt(fmt(orig_dt), False)
                + "  →  "
                + _fmt(fmt(sup_dt), not same_dt),
                unsafe_allow_html=True
            )
        else:
            st.markdown("**Proposed Delivery Date:** Not specified")

        # -------- table header ----------
        col_title = st.columns([3, 2, 2, 2, 2])
        headers   = ["Item", "Orig Qty", "Prop Qty",
                     "Orig Price", "Prop Price"]
        for c, h in zip(col_title, headers):
            c.write(f"**{h}**")

        # -------- each PO line ----------
        for _, row in po_data.iterrows():
            row_cols = st.columns([3, 2, 2, 2, 2])

            # comparisons
            qty_changed   = not _same(row["orderedquantity"],
                                       row["supproposedquantity"])
            price_changed = not _same(row["estimatedprice"],
                                       row["supproposedprice"])

            # item name (always plain)
            row_cols[0].write(row["itemnameenglish"])

            # quantities
            row_cols[1].markdown(
                _fmt(row["orderedquantity"] or "N/A", False),
                unsafe_allow_html=True)
            row_cols[2].markdown(
                _fmt(row["supproposedquantity"] or "N/A", qty_changed),
                unsafe_allow_html=True)

            # prices
            orig_price = (f"${row['estimatedprice']:.2f}"
                          if pd.notnull(row["estimatedprice"]) else "N/A")
            prop_price = (f"${row['supproposedprice']:.2f}"
                          if pd.notnull(row["supproposedprice"]) else "N/A")

            row_cols[3].markdown(_fmt(orig_price, False), unsafe_allow_html=True)
            row_cols[4].markdown(_fmt(prop_price, price_changed),
                                 unsafe_allow_html=True)

        # -------- action buttons ----------
        col_accept, col_modify, col_decline = st.columns(3)

        if col_accept.button(f"✅ Accept Proposal #{poid}", key=f"accept_{poid}"):
            new_poid = po_handler.accept_proposed_po(poid)
            st.success(f"Proposal accepted. New PO #{new_poid} created.")
            st.rerun()

        if col_modify.button(f"✏️ Modify Proposal #{poid}", key=f"modify_{poid}"):
            st.session_state[f"show_modify_form_{poid}"] = True

        if st.session_state.get(f"show_modify_form_{poid}", False):
            _show_modify_form(po_handler, poid, po_data)

        if col_decline.button(f"❌ Decline Proposal #{poid}", key=f"decline_{poid}"):
            po_handler.decline_proposed_po(poid)
            st.warning(f"Proposal #{poid} declined (status: 'Declined by AMAS').")
            st.rerun()

        st.markdown("---")


# ───────────────── modify‑form logic (unchanged) ─────────────────
def _show_modify_form(po_handler, poid, po_data):
    st.markdown("### ✏️ Modify Proposal")
    sup_date = po_data.iloc[0].get("sup_proposeddeliver")
    default_date = date.today()
    default_time = time(hour=9)
    if pd.notnull(sup_date):
        dts = pd.to_datetime(sup_date)
        default_date, default_time = dts.date(), dts.time()

    with st.form(key=f"modify_form_{poid}", clear_on_submit=True):
        user_date = st.date_input("New Delivery Date",
                                  default_date,
                                  key=f"user_date_{poid}")
        user_time = st.time_input("New Delivery Time",
                                  default_time,
                                  key=f"user_time_{poid}")

        mod_items = []
        st.write("### Edit Item Lines")

        for _, row in po_data.iterrows():
            st.write(f"**{row['itemnameenglish']}**")
            c1, c2 = st.columns(2)

            default_qty = (
                row["supproposedquantity"]
                if pd.notnull(row["supproposedquantity"])
                else row["orderedquantity"] or 1
            )
            user_qty = c1.number_input(
                f"Qty (PO {poid}, Item {row['itemid']})",
                min_value=1,
                value=int(default_qty),
                step=1,
                key=f"user_qty_{poid}_{row['itemid']}"
            )

            fallback_price = (
                row["supproposedprice"]
                if pd.notnull(row["supproposedprice"])
                else row.get("estimatedprice", 0.0) or 0.0
            )
            user_price = c2.number_input(
                f"Price (PO {poid}, Item {row['itemid']})",
                value=float(fallback_price),
                step=0.01,
                key=f"user_price_{poid}_{row['itemid']}"
            )

            mod_items.append({
                "item_id": row["itemid"],
                "quantity": user_qty,
                "estimated_price": user_price
            })

        if st.form_submit_button("Submit Modified Proposal"):
            user_dt = datetime.combine(user_date, user_time)
            new_poid = po_handler.modify_proposed_po(
                proposed_po_id=poid,
                new_delivery_date=user_dt,
                new_items=mod_items,
                user_email=st.session_state.get("user_email", "Unknown")
            )
            st.success(
                f"✅ New PO #{new_poid} created from modifications. "
                f"Original PO marked as 'Modified by AMAS'."
            )
            st.session_state[f"show_modify_form_{poid}"] = False
            st.rerun()
