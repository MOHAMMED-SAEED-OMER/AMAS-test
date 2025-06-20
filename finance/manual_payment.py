import streamlit as st
import pandas as pd
from typing import Dict

# ─────────────────────────────────────────────────────────────
# Helper to store / fetch the per‑supplier allocation dict
# ─────────────────────────────────────────────────────────────
def _get_alloc_dict(supplier_id: int) -> Dict[int, float]:
    key = f"_alloc_dict_{supplier_id}"
    if key not in st.session_state:
        st.session_state[key] = {}          # {poid: amount}
    return st.session_state[key]


def handle_manual_allocation(
    fh,
    supplier_id: int,
    payment_date,
    payment_method: str,
    amount: float,
    notes: str,
):
    """Interactive manual allocation UI/logic."""
    st.subheader("🖐️ Manual allocation")

    # ── outstanding POs for this supplier ────────────────────
    po_df = fh.get_outstanding_pos_by_supplier(supplier_id)
    if po_df.empty:
        st.info("No open POs to allocate.")
        return

    alloc = _get_alloc_dict(supplier_id)          # current allocations
    remaining = amount - sum(alloc.values())

    st.markdown(f"**Remaining to allocate:** `{remaining:.2f}`")

    # ---------- PO table with number_inputs & Fill buttons ---------------
    for _, row in po_df.iterrows():
        poid   = int(row["poid"])
        owing  = float(row["outstanding_amount"])
        cur    = alloc.get(poid, 0.0)

        cols = st.columns([2, 2, 2, 1])
        cols[0].markdown(f"**PO #{poid}**  <br/><small>{row['order_date']}</small>",
                         unsafe_allow_html=True)
        cols[1].markdown(f"Owing: **{owing:.2f}**")
        # editable field
        new_val = cols[2].number_input(
            "Alloc",
            min_value=0.0,
            max_value=owing,
            value=cur,
            step=0.01,
            key=f"alloc_input_{supplier_id}_{poid}",
        )

        # update dict if user typed a value
        if new_val != cur:
            alloc[poid] = new_val

        # “Fill” = assign as much as possible
        if cols[3].button("Fill", key=f"fill_{supplier_id}_{poid}"):
            remaining_now = amount - sum(alloc.values())  # after any typing
            fill_amt = min(remaining_now, owing)
            alloc[poid] = fill_amt
            # no mutation of widget after creation: rely on rerun
            st.rerun()

    # ---------- SUBMIT ----------------------------------------------------
    total_alloc = sum(alloc.values())
    if total_alloc != amount:
        st.warning("Allocated total must equal the payment amount before saving.")
        return

    if st.button("✅ SAVE allocation & payment"):
        pay_id = fh.create_supplier_payment(
            supplier_id=supplier_id,
            payment_date=payment_date,
            amount=amount,
            method=payment_method,
            notes=notes,
        )
        if not pay_id:
            st.error("Failed to store payment.")
            return

        for poid, alloc_amt in alloc.items():
            status = "Full" if abs(alloc_amt -          # fully paid?
                                   float(po_df.loc[po_df.poid == poid,
                                                   "outstanding_amount"].values[0])) < 1e-6 \
                     else "Partial"
            fh.allocate_payment(pay_id, poid, alloc_amt, status)

        # clear allocation dict
        st.session_state.pop(f"_alloc_dict_{supplier_id}", None)
        st.success(f"Payment #{pay_id} recorded and allocated.")
        st.rerun()
