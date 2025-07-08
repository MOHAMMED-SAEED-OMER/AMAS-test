# finance/supplier_debts.py  – MySQL backend
import streamlit as st
import pandas as pd

from finance.finance_handler import FinanceHandler

fh = FinanceHandler()

# ───────────────────────── helper queries ─────────────────────────
def _load_supplier_debt_summary() -> pd.DataFrame:
    """
    Total consignment received – total paid, by supplier.
    """
    sql = """
        WITH received AS (
            SELECT  po.supplierid,
                    SUM(pc.quantity * pc.cost_per_unit)  AS total_received
            FROM    `poitemcost` pc
            JOIN    `purchaseorders` po ON pc.poid = po.poid
            GROUP   BY po.supplierid
        ),
        paid AS (
            SELECT  po.supplierid,
                    SUM(pp.allocatedamount)             AS total_paid
            FROM    `popayments`   pp
            JOIN    `purchaseorders` po ON pp.poid = po.poid
            GROUP   BY po.supplierid
        )
        SELECT  s.supplierid,
                s.suppliername,
                COALESCE(r.total_received, 0)                   AS total_received,
                COALESCE(p.total_paid,     0)                   AS total_paid,
                COALESCE(r.total_received, 0) -
                COALESCE(p.total_paid,     0)                   AS total_outstanding
        FROM    `supplier` s
        LEFT JOIN received r ON r.supplierid = s.supplierid
        LEFT JOIN paid     p ON p.supplierid = s.supplierid
        WHERE   COALESCE(r.total_received, 0) > 0
        ORDER   BY s.suppliername
    """
    return fh.fetch_data(sql)


def _load_overdue_po_alerts(days: int) -> pd.DataFrame:
    """
    List POs whose consignment balance is older than <days>.
    """
    sql = f"""
        WITH po_totals AS (
            SELECT  poid,
                    SUM(quantity * cost_per_unit) AS received_value
            FROM    `poitemcost`
            GROUP   BY poid
        ),
        po_paid AS (
            SELECT  poid,
                    SUM(allocatedamount)          AS paid_value
            FROM    `popayments`
            GROUP   BY poid
        )
        SELECT  s.suppliername,
                p.poid,
                p.actualdelivery,
                DATEDIFF(CURDATE(), p.actualdelivery)           AS days_old,
                COALESCE(t.received_value, 0) -
                COALESCE(pa.paid_value,   0)                    AS outstanding
        FROM    `purchaseorders` p
        JOIN    `supplier`       s USING (supplierid)
        LEFT JOIN po_totals t  ON t.poid = p.poid
        LEFT JOIN po_paid   pa ON pa.poid = p.poid
        WHERE   (COALESCE(t.received_value,0) -
                 COALESCE(pa.paid_value,  0)) > 0
          AND   DATEDIFF(CURDATE(), p.actualdelivery) > {days}
        ORDER   BY days_old DESC, p.poid
    """
    return fh.fetch_data(sql)


def _load_supplier_po_detail(supplier_id: int) -> pd.DataFrame:
    """
    Outstanding consignment per-PO for a given supplier.
    """
    sql = """
        WITH po_totals AS (
            SELECT  poid,
                    SUM(quantity * cost_per_unit) AS received_value
            FROM    `poitemcost`
            WHERE   poid IN (SELECT poid
                             FROM   `purchaseorders`
                             WHERE  supplierid = %s)
            GROUP   BY poid
        ),
        po_paid AS (
            SELECT  poid,
                    SUM(allocatedamount)          AS paid_value
            FROM    `popayments`
            GROUP   BY poid
        )
        SELECT  p.poid,
                p.orderdate,
                p.actualdelivery,
                COALESCE(t.received_value, 0)                   AS received_value,
                COALESCE(pa.paid_value,    0)                   AS paid_value,
                COALESCE(t.received_value, 0) -
                COALESCE(pa.paid_value,    0)                   AS outstanding
        FROM    `purchaseorders` p
        LEFT JOIN po_totals t ON t.poid = p.poid
        LEFT JOIN po_paid   pa ON pa.poid = p.poid
        WHERE   p.supplierid = %s
          AND   (COALESCE(t.received_value, 0) -
                 COALESCE(pa.paid_value,    0)) <> 0   -- 👈 filter without alias
        ORDER   BY p.actualdelivery, p.poid
    """
    return fh.fetch_data(sql, (supplier_id, supplier_id))


# ─────────────────────────── UI tab ──────────────────────────────
def supplier_debts_tab():
    st.header("📑 Supplier Debts")

    summary_df = _load_supplier_debt_summary()
    if summary_df.empty:
        st.success("Great! No supplier has unpaid consignment balance.")
        return

    # 1️⃣  Summary table -------------------------------------------------
    st.dataframe(
        summary_df.rename(
            columns={
                "suppliername": "Supplier",
                "total_received": "Total Received Amt",
                "total_paid": "Total Paid",
                "total_outstanding": "Total Outstanding",
            }
        ).style.format(
            {
                "Total Received Amt": "{:,.2f}",
                "Total Paid": "{:,.2f}",
                "Total Outstanding": "{:,.2f}",
            }
        ),
        use_container_width=True,
    )

    # 2️⃣  Over-due Debts section ---------------------------------------
    st.markdown("---")
    st.markdown("## 🚨 Over-due Debts")

    alert_days = st.number_input(
        "Show debts older than (days)", min_value=1, value=30, step=1
    )
    alert_df = _load_overdue_po_alerts(alert_days)

    if alert_df.empty:
        st.success(
            f"All clear! No PO has been outstanding for more than {alert_days} days."
        )
    else:
        left, right = st.columns([3, 1])

        with left:
            st.dataframe(
                alert_df.rename(
                    columns={
                        "suppliername": "Supplier",
                        "poid": "PO #",
                        "actualdelivery": "Delivery",
                        "days_old": "Days Old",
                        "outstanding": "Outstanding",
                    }
                ).style.format({"Outstanding": "{:,.2f}"}),
                use_container_width=True,
            )

        with right:
            sup_totals = (
                alert_df.groupby("suppliername", as_index=False)
                .agg(outstanding=("outstanding", "sum"))
                .sort_values("outstanding", ascending=False)
            )
            st.markdown("#### Totals")
            st.dataframe(
                sup_totals.rename(
                    columns={"suppliername": "Supplier", "outstanding": "Outstanding"}
                ).style.format({"Outstanding": "{:,.2f}"}),
                hide_index=True,
                use_container_width=True,
            )

    # 3️⃣  Drill-down per supplier --------------------------------------
    st.markdown("---")
    st.subheader("🔍 View Outstanding POs for a Supplier")

    supplier_lookup = dict(zip(summary_df.suppliername, summary_df.supplierid))
    sel_name = st.selectbox(
        "Choose Supplier", list(supplier_lookup.keys()), key="debt_supplier_select"
    )

    if sel_name:
        sel_id = supplier_lookup[sel_name]
        detail_df = _load_supplier_po_detail(sel_id)

        if detail_df.empty:
            st.info("This supplier has no open POs.")
            st.markdown(f"**Total outstanding for {sel_name}: 0 IQD**")
        else:
            total_out = detail_df["outstanding"].sum()
            st.markdown(
                f"**Total outstanding for {sel_name}: {total_out:,.2f} IQD**"
            )

            st.dataframe(
                detail_df[
                    [
                        "poid",
                        "orderdate",
                        "actualdelivery",
                        "received_value",
                        "paid_value",
                        "outstanding",
                    ]
                ].rename(
                    columns={
                        "poid": "PO #",
                        "orderdate": "Order Date",
                        "actualdelivery": "Delivery",
                        "received_value": "Received Amt",
                        "paid_value": "Paid",
                        "outstanding": "Outstanding",
                    }
                ).style.format(
                    {
                        "Received Amt": "{:,.2f}",
                        "Paid": "{:,.2f}",
                        "Outstanding": "{:,.2f}",
                    }
                ),
                use_container_width=True,
            )
