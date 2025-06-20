import streamlit as st
from finance.finance_handler import FinanceHandler
from finance.manual_payment import handle_manual_allocation
from finance.consignment_payment import consignment_tab  # 👈 Import new tab

fh = FinanceHandler()

def sup_payment_tab():
    st.header("💵 Supplier Payments")

    # Tab Layout
    tabs = st.tabs(["💳 Standard Payment", "📦 Consignment Payment"])

    with tabs[0]:
        show_standard_payment_tab()

    with tabs[1]:
        consignment_tab(fh)

# ───────────────────────────────────────────────────────────────
# This contains the original logic you already have.
def show_standard_payment_tab():
    # ─────────────────── supplier selector ────────────────────
    sup_df = fh.fetch_data(
        "SELECT supplierid, suppliername FROM supplier ORDER BY suppliername"
    )
    if sup_df.empty:
        st.info("No suppliers.")
        return

    sup_map  = dict(zip(sup_df.suppliername, sup_df.supplierid))
    sel_name = st.selectbox(
        "Choose Supplier",
        list(sup_map.keys()),
        key="payment_supplier_select"
    )
    supplier_id = sup_map[sel_name]

    # ─────────────────── Total outstanding ────────────────────
    po_df = fh.get_outstanding_pos_by_supplier(supplier_id)
    owed_val = float(po_df["outstanding_amount"].sum()) if not po_df.empty else 0.0
    st.markdown(f"### Total outstanding: **{owed_val:.2f}**")

    # ───────────────── payment details ────────────────────────
    col_left, col_right = st.columns([2, 1])
    with col_left:
        pay_date   = st.date_input("Payment date")
        amount     = st.number_input("Amount", min_value=0.01, step=0.01, format="%.2f")
        pay_method = st.selectbox("Method", ["Cash", "Credit Card", "Bank Transfer", "Other"])
        notes      = st.text_area("Notes (optional)")

    with col_right:
        alloc_mode = st.radio("Allocation style", ["Automatic", "Manual"], key="alloc_style")

    st.markdown("---")

    # ───────────────── buttons ────────────────────────────────
    if alloc_mode == "Automatic":
        if st.button("💾 Create payment & auto‑allocate"):
            if amount <= 0:
                st.error("Enter a positive amount.")
                return

            pay_id = fh.create_supplier_payment(
                supplier_id=supplier_id,
                payment_date=pay_date,
                amount=amount,
                method=pay_method,
                notes=notes,
            )
            if not pay_id:
                st.error("DB error while creating payment.")
                return

            rem       = amount
            alloc_cnt = 0
            for _, po in po_df.iterrows():
                if rem <= 0:
                    break
                owe   = float(po["outstanding_amount"])
                alloc = min(rem, owe)
                status = "Full" if alloc == owe else "Partial"
                fh.allocate_payment(pay_id, int(po["poid"]), alloc, status)
                rem -= alloc
                alloc_cnt += 1

            st.success(f"Payment #{pay_id} saved. Allocated {amount-rem:.2f} across {alloc_cnt} PO(s).")
            st.rerun()

    else:  # Manual allocation
        handle_manual_allocation(
            fh, supplier_id, pay_date, pay_method, amount, notes
        )

    # ───────────────── outstanding POs table (always) ─────────
    st.markdown("---")
    st.markdown("#### 🔎 Outstanding Purchase Orders")
    if po_df.empty:
        st.info("No open POs for this supplier.")
    else:
        st.dataframe(
            po_df.rename(columns={
                "poid": "PO #",
                "order_date": "Date",
                "totalcost": "Total Cost",
                "paid_amount": "Paid",
                "outstanding_amount": "Remaining",
            }),
            hide_index=True,
            use_container_width=True,
        )
