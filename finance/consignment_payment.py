# finance/consignment_payment.py
"""
Consignment dashboard (MySQL backend)

• Outstanding debt  =  Σ(received per PO) – Σ(payments per PO)
• Unsold consignment stock still with us (inventory + shelf) and its value
• Record consignment payments (FIFO — oldest partially/unpaid POs first)
"""
import pandas as pd
import streamlit as st

from finance.finance_handler import FinanceHandler


# ────────────────────────────────────────────────────────────────
def consignment_tab(fh: FinanceHandler) -> None:
    st.header("📦 Consignment Payments")

    # 1️⃣  Supplier selector
    sup_df = fh.fetch_data(
        "SELECT supplierid, suppliername FROM `supplier` ORDER BY suppliername"
    )
    if sup_df.empty:
        st.info("No suppliers found.")
        return

    lookup = dict(zip(sup_df["supplierid"], sup_df["suppliername"]))
    supplier_id = st.selectbox(
        "Supplier", sup_df["supplierid"], format_func=lambda sid: lookup[sid]
    )
    if supplier_id is None:
        st.stop()

    _render_supplier_dashboard(fh, supplier_id, lookup[supplier_id])


# ────────────────────────────────────────────────────────────────
def _render_supplier_dashboard(
    fh: FinanceHandler, supplier_id: int, supplier_name: str
):
    st.subheader(f"Supplier: {supplier_name}")

    # 2️⃣  Item-level receipt rows (from poitemcost)
    po_items_sql = """
        WITH received AS (
            SELECT  pc.poid,
                    pc.itemid,
                    it.itemnameenglish                    AS itemname,
                    SUM(pc.quantity)                      AS received_qty,
                    AVG(pc.cost_per_unit)                 AS cost_per_unit,
                    SUM(pc.quantity * pc.cost_per_unit)   AS received_value,
                    MIN(po.actualdelivery)                AS order_date
            FROM    `poitemcost`        pc
            JOIN    `purchaseorders`    po ON pc.poid  = po.poid
            JOIN    `item`              it ON pc.itemid = it.itemid
            WHERE   po.supplierid = %s
            GROUP BY pc.poid, pc.itemid, it.itemnameenglish
        )
        SELECT * FROM received
    """
    po_items_df = fh.fetch_data(po_items_sql, (supplier_id,))
    if po_items_df.empty:
        st.info("This supplier has no consignment cost rows.")
        return

    po_items_df[["cost_per_unit", "received_value"]] = po_items_df[
        ["cost_per_unit", "received_value"]
    ].astype(float)

    # 3️⃣  PO-level totals
    po_totals = (
        po_items_df.groupby("poid", as_index=False)
        .agg(
            received_value=("received_value", "sum"),
            order_date=("order_date", "first"),
        )
    )

    # payments per PO
    paid_map = (
        fh.fetch_data(
            """
            SELECT poid,
                   SUM(allocatedamount) AS paid_amount
            FROM   `popayments`
            GROUP  BY poid
            """
        )
        .set_index("poid")["paid_amount"]
        .to_dict()
    )

    po_totals["paid_amount"] = po_totals["poid"].map(paid_map).fillna(0.0)
    po_totals["outstanding"] = po_totals["received_value"] - po_totals["paid_amount"]

    outstanding_total = po_totals["outstanding"].sum()
    st.markdown(f"### 💰 Outstanding debt: **{outstanding_total:,.2f} IQD**")

    with st.expander("🔍 PO breakdown"):
        st.dataframe(
            po_totals[["poid", "received_value", "paid_amount", "outstanding"]],
            use_container_width=True,
            hide_index=True,
        )

    # 4️⃣  Stock on hand — exact valuation
    stock_sql = """
        /* Inventory part */
        SELECT  i.itemid,
                SUM(i.quantity)                        AS inv_qty,
                0                                      AS shelf_qty,
                SUM(i.quantity * i.cost_per_unit)      AS inv_value,
                0                                      AS shelf_value
        FROM    `inventory`      i
        JOIN    `itemsupplier`   s ON i.itemid = s.itemid
        WHERE   s.supplierid = %s
        GROUP BY i.itemid

        UNION ALL

        /* Shelf part */
        SELECT  sh.itemid,
                0                                      AS inv_qty,
                SUM(sh.quantity)                       AS shelf_qty,
                0                                      AS inv_value,
                SUM(sh.quantity * sh.cost_per_unit)    AS shelf_value
        FROM    `shelf`         sh
        JOIN    `itemsupplier`  s ON sh.itemid = s.itemid
        WHERE   s.supplierid = %s
        GROUP BY sh.itemid
    """
    stock_raw = fh.fetch_data(stock_sql, (supplier_id, supplier_id))

    if stock_raw.empty:
        total_qty, total_value = 0, 0.0
        stock_df = pd.DataFrame()
    else:
        stock_df = (
            stock_raw.groupby("itemid", as_index=False)
            .agg(
                inv_qty=("inv_qty", "sum"),
                shelf_qty=("shelf_qty", "sum"),
                inv_value=("inv_value", "sum"),
                shelf_value=("shelf_value", "sum"),
            )
        )
        stock_df["total_qty"] = stock_df["inv_qty"] + stock_df["shelf_qty"]
        stock_df["total_value"] = stock_df["inv_value"] + stock_df["shelf_value"]

        names_df = fh.fetch_data(
            "SELECT itemid, itemnameenglish AS itemname FROM `item`"
        )
        stock_df = stock_df.merge(names_df, on="itemid", how="left")

        total_qty = int(stock_df["total_qty"].sum())
        total_value = stock_df["total_value"].sum()

    st.markdown(f"### 📦 Stock on hand: **{total_qty:,} units**")
    st.markdown(f"### 💵 Stock value: **{total_value:,.2f} IQD**")

    if not stock_df.empty:
        with st.expander("🔍 Stock breakdown"):
            st.dataframe(
                stock_df[
                    [
                        "itemid",
                        "itemname",
                        "inv_qty",
                        "shelf_qty",
                        "total_qty",
                        "total_value",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )

    # 5️⃣  Payment form + automatic FIFO allocation
    st.markdown("---")
    st.markdown("## 💸 Record a consignment payment (FIFO)")

    pay_cols = st.columns([2, 1, 1, 3])
    pay_date = pay_cols[0].date_input("Payment date", value=pd.Timestamp.today())
    pay_method = pay_cols[1].selectbox(
        "Method", ["Cash", "Credit Card", "Bank Transfer", "Other"], key="consign_pay_method"
    )
    amount = pay_cols[2].number_input(
        "Amount", min_value=0.01, step=0.01, format="%.2f", key="consign_pay_amount"
    )
    notes = pay_cols[3].text_input("Notes (optional)")

    if st.button("💾 Pay & auto-allocate (oldest first)"):
        if amount <= 0:
            st.error("Enter a positive amount.")
            st.stop()

        pay_id = fh.create_supplier_payment(
            supplier_id=supplier_id,
            payment_date=pay_date,
            amount=amount,
            method=pay_method,
            notes=notes,
            payment_type="Consignment",
        )
        if not pay_id:
            st.error("DB error creating payment.")
            st.stop()

        # FIFO allocation
        po_fifo = (
            po_totals.query("outstanding > 0")
            .sort_values(["order_date", "poid"])
            .reset_index(drop=True)
        )

        rem = amount
        alloc_cnt = 0
        for r in po_fifo.itertuples():
            if rem <= 0:
                break
            pay_amt = min(rem, r.outstanding)
            status = "Full" if pay_amt == r.outstanding else "Partial"
            fh.allocate_payment(pay_id, int(r.poid), pay_amt, status)
            rem -= pay_amt
            alloc_cnt += 1

        st.success(
            f"✅ Payment #{pay_id} recorded. "
            f"Allocated {amount - rem:,.2f} across {alloc_cnt} PO(s)."
        )
        st.rerun()

    # 6️⃣  Amount-payable summary
    payable = max(0.0, outstanding_total - total_value)
    st.markdown("---")
    st.markdown(f"### Amount payable now (consignment): **{payable:,.2f} IQD**")
    st.markdown("---")
