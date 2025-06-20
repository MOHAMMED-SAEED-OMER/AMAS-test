# returns/track_return.py
import streamlit as st
import pandas as pd

from returns.return_handler   import ReturnHandler
from finance.finance_handler  import FinanceHandler      # payment/allocation

rh  = ReturnHandler()
fin = FinanceHandler()

# ────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────
def _deduct_inventory(ret_id: int) -> None:
    """Subtract returned quantity from inventory (batch aware)."""
    lines = rh.get_return_items(ret_id)
    for _, ln in lines.iterrows():
        if pd.isna(ln["expirationdate"]):
            continue
        rh.reduce_inventory(
            itemid     = int(ln["itemid"]),
            expiredate = str(ln["expirationdate"]),
            qty        = int(ln["quantity"]),
        )

def _allocate_credit_payment(ret_id: int, header: pd.Series) -> None:
    """
    • Insert a row in *supplierpayments* (method='Return Credit')
    • Insert rows in *popayments*           (strict PO links first,
                                             remainder oldest-unpaid)
    """
    # 1️⃣ create supplierpayments header
    pay_id = fin.create_supplier_payment(
        supplier_id  = int(header["supplierid"]),
        payment_date = header["approvedate"],
        amount       = float(header["totalreturncost"]),
        method       = "Return Credit",
        notes        = f"Return #{ret_id}",
    )

    # 2️⃣ get strict PO allocations (i.e. POID was set on return lines)
    strict_lines = rh.get_return_items(ret_id)
    strict_lines = strict_lines.dropna(subset=["poid"])
    strict_tot   = (
        strict_lines.groupby("poid")["totalcost"]
        .sum()
        .reset_index()
    )

    allocated   = 0.0
    outstanding = fin.get_outstanding_pos_by_supplier(int(header["supplierid"]))

    # helper → how much still owed on a PO *right now*
    def _owed(poid: int) -> float:
        row = outstanding.loc[outstanding["poid"] == poid]
        return float(row["outstanding_amount"].iloc[0]) if not row.empty else 0.0

    # 2-a) apply strict allocations exactly
    for _, row in strict_tot.iterrows():
        poid  = int(row["poid"])
        alloc = float(row["totalcost"])
        status = "Full" if abs(alloc - _owed(poid)) < 0.01 else "Partial"
        fin.allocate_payment(pay_id, poid, alloc, status, return_id=ret_id)
        allocated += alloc

    # 3️⃣ auto-allocate any remaining credit
    remaining = float(header["totalreturncost"]) - allocated
    if remaining <= 0.009:
        return

    # identify whichever date column we got back from the DB
    candidate_cols = ["order_date", "orderdate", "orderDate"]
    sort_col       = next((c for c in candidate_cols if c in outstanding.columns), None)
    iterable_df    = outstanding if sort_col is None else outstanding.sort_values(sort_col)

    for _, po in iterable_df.iterrows():
        poid = int(po["poid"])
        if poid in strict_tot["poid"].tolist():        # skip already-allocated strict POs
            continue

        owe = float(po["outstanding_amount"])
        if owe <= 0.009:
            continue

        alloc  = min(remaining, owe)
        status = "Full" if alloc == owe else "Partial"
        fin.allocate_payment(pay_id, poid, alloc, status, return_id=ret_id)
        remaining -= alloc
        if remaining <= 0.009:
            break

# ────────────────────────────────────────────────────────────────
# Approve / Reject actions
# ────────────────────────────────────────────────────────────────
def _approve_return(ret_id: int, credit_note: str, user_email: str):
    """Mark as approved, deduct inventory, create credit payment."""
    rh.execute_command(
        """
        UPDATE supplierreturns
           SET returnstatus = 'Approved',
               creditnote   = %s,
               approvedby   = %s,
               approvedate  = CURRENT_TIMESTAMP
         WHERE returnid     = %s
        """,
        (credit_note, user_email, ret_id),
    )

    header = rh.get_return_header(ret_id).iloc[0]
    _deduct_inventory(ret_id)
    _allocate_credit_payment(ret_id, header)

def _reject_return(ret_id: int, user_email: str):
    rh.execute_command(
        """
        UPDATE supplierreturns
           SET returnstatus = 'Rejected',
               approvedby   = %s,
               approvedate  = CURRENT_TIMESTAMP
         WHERE returnid     = %s
        """,
        (user_email, ret_id),
    )

# ────────────────────────────────────────────────────────────────
# Main tab
# ────────────────────────────────────────────────────────────────
def track_returns_tab() -> None:
    st.header("📋 Track Supplier Returns")

    df = rh.get_returns_summary()
    if df.empty:
        st.info("No returns recorded yet.")
        return

    # ----- filters ----------------------------------------------------
    suppliers = ["All"] + sorted(df["suppliername"].unique())
    f_sup = st.selectbox("Supplier", suppliers)
    if f_sup != "All":
        df = df[df["suppliername"] == f_sup]

    df["createddate"] = pd.to_datetime(df["createddate"])
    f_start, f_end = st.date_input(
        "Date range",
        (df["createddate"].dt.date.min(), df["createddate"].dt.date.max()),
    )
    df = df[
        (df["createddate"].dt.date >= f_start)
        & (df["createddate"].dt.date <= f_end)
    ]

    # ----- summary grid ----------------------------------------------
    st.dataframe(
        df.rename(
            columns={
                "returnid":        "Return #",
                "suppliername":    "Supplier",
                "createddate":     "Created",
                "returnstatus":    "Status",
                "totalreturncost": "Total",
            }
        ),
        hide_index=True,
        use_container_width=True,
    )
    st.markdown("---")

    # ----- drill-down -------------------------------------------------
    sel = st.selectbox(
        "Choose a return",
        df["returnid"].astype(str),
        format_func=lambda x: f"Return #{x}",
    )
    if not sel:
        return
    ret_id = int(sel)

    header = rh.get_return_header(ret_id).iloc[0]
    lines  = rh.get_return_items(ret_id)

    st.subheader(f"Return #{ret_id} – {header['returnstatus']}")
    st.write(f"**Supplier ID:** {header['supplierid']}")
    st.write(f"**Created:** {header['createddate']}")
    st.write(f"**Total Cost:** {header['totalreturncost']:.2f}")
    st.write(f"**Credit-note:** {header.get('creditnote') or '—'}")
    st.write(f"**Notes:** {header.get('notes') or '—'}")
    if pd.notna(header["approvedate"]):
        st.write(f"**Approved:** {header['approvedate']} by {header.get('approvedby','–')}")

    # line-items table
    st.markdown("#### Items")
    st.dataframe(
        lines[
            [
                "itemid",
                "itemnameenglish",
                "quantity",
                "itemprice",
                "totalcost",
                "expirationdate",
                "poid",
                "reason",
            ]
        ].rename(
            columns={
                "itemid":        "Item",
                "itemnameenglish": "Name",
                "quantity":      "Qty",
                "itemprice":     "Unit",
                "totalcost":     "Total",
                "expirationdate":"Expiry",
                "poid":          "PO",
                "reason":        "Reason",
            }
        ),
        hide_index=True,
        use_container_width=True,
    )

    # action buttons when pending
    if header["returnstatus"] == "Pending Approval":
        st.markdown("### Action")
        credit_note = st.text_input("Supplier credit-note # (required)")
        col_a, col_r = st.columns(2)
        if col_a.button("✅ Approve", disabled=not credit_note, type="primary"):
            _approve_return(ret_id, credit_note, st.session_state["user_email"])
            st.success("Return approved. Inventory & supplier debt updated.")
            st.rerun()
        if col_r.button("❌ Reject", type="secondary"):
            _reject_return(ret_id, st.session_state["user_email"])
            st.warning("Return rejected.")
            st.rerun()
