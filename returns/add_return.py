# inventory/returns/add_return.py
import streamlit as st
from returns.return_handler import ReturnHandler

rh = ReturnHandler()

# ───────────────────────────────────────────────────────────────
def return_tab() -> None:
    st.header("🔁 Create Supplier Return")

    # 1) Supplier selector ───────────────────────────────────────
    sup_df = rh.fetch_data(
        "SELECT supplierid, suppliername FROM supplier ORDER BY suppliername"
    )
    if sup_df.empty:
        st.info("No suppliers in database.")
        return

    supplier_id = st.selectbox(
        "Supplier",
        sup_df.supplierid.tolist(),
        format_func=lambda sid: sup_df.loc[
            sup_df.supplierid == sid, "suppliername"
        ].values[0],
    )

    st.markdown("---")

    # 2) Number of lines ─────────────────────────────────────────
    max_rows = 15
    n_rows = st.number_input(
        "How many different items to return?",
        min_value=1,
        max_value=max_rows,
        value=1,
        step=1,
        key="ret_nrows",
    )

    # 3) Item & PO look-ups ─────────────────────────────────────
    items_df = rh.fetch_data(
        """
        SELECT i.itemid, i.itemnameenglish
          FROM item i
          JOIN itemsupplier isup ON i.itemid = isup.itemid
         WHERE isup.supplierid = %s
         ORDER BY i.itemnameenglish
        """,
        (supplier_id,),
    )
    if items_df.empty:
        st.warning("No items assigned to this supplier yet.")
        return

    po_df = rh.fetch_data(
        "SELECT poid FROM purchaseorders WHERE supplierid = %s ORDER BY poid DESC",
        (supplier_id,),
    )
    po_choices = ["—"] + po_df["poid"].astype(str).tolist()

    # session store for draft lines
    if (
        "return_lines" not in st.session_state
        or len(st.session_state.return_lines) != int(n_rows)
    ):
        st.session_state.return_lines = [{} for _ in range(int(n_rows))]

    # ────────────────────────────────────────────────────────────
    #  Header row (8 columns)
    # ────────────────────────────────────────────────────────────
    hdr_item, hdr_exp, hdr_qty, hdr_price, hdr_reason, hdr_poid, hdr_max, hdr_avg = \
        st.columns([3, 2, 1, 1, 2, 1, 1, 1])

    hdr_item.markdown("**Item**")
    hdr_exp.markdown("**Expiry**")
    hdr_qty.markdown("**Qty**")
    hdr_price.markdown("**Unit&nbsp;Price**")
    hdr_reason.markdown("**Reason**")
    hdr_poid.markdown("**Linked&nbsp;PO**")
    hdr_max.markdown("**Max**")
    hdr_avg.markdown("**cost**")

    # ────────────────────────────────────────────────────────────
    #  Data rows
    # ────────────────────────────────────────────────────────────
    for idx in range(int(n_rows)):
        (
            col_item, col_exp, col_qty, col_price,
            col_reason, col_poid, col_max, col_avg
        ) = st.columns([3, 2, 1, 1, 2, 1, 1, 1])

        # Item selector
        item_name = col_item.selectbox(
            "",
            items_df.itemnameenglish,
            key=f"item_{idx}",
            label_visibility="collapsed",
        )
        item_id = int(
            items_df.loc[items_df.itemnameenglish == item_name, "itemid"].values[0]
        )

        # Expiry + available quantity (Inventory ∪ Shelf)
        exp_df = rh.fetch_data(
            """
            SELECT expirationdate,
                   SUM(q)::int AS quantity
            FROM (
                SELECT expirationdate, quantity AS q
                  FROM inventory WHERE itemid = %s
                UNION ALL
                SELECT expirationdate, quantity AS q
                  FROM shelf      WHERE itemid = %s
            ) z
            GROUP BY expirationdate HAVING SUM(q) > 0
            ORDER  BY expirationdate;
            """,
            (item_id, item_id),
        )

        if exp_df.empty:
            exp_opt      = col_exp.selectbox(
                "", ["—"], key=f"exp_{idx}", label_visibility="collapsed"
            )
            exp_selected = None
            avail_qty    = 0
        else:
            opts = [
                f"{r.expirationdate} (Qty {r.quantity})"
                for _, r in exp_df.iterrows()
            ]
            exp_opt = col_exp.selectbox(
                "", opts, key=f"exp_{idx}", label_visibility="collapsed"
            )
            exp_selected = str(
                exp_df.iloc[opts.index(exp_opt)].expirationdate
            )
            avail_qty = exp_df.iloc[opts.index(exp_opt)].quantity

        # Qty input
        qty = col_qty.number_input(
            "",
            min_value=1,
            max_value=max(avail_qty, 1),
            value=1,
            step=1,
            key=f"qty_{idx}",
            label_visibility="collapsed",
        )

        # Weighted-average cost (Inventory ∪ Shelf)
        avg_cost_df = rh.fetch_data(
            """
            WITH layers AS (
              SELECT quantity, cost_per_unit
                FROM inventory WHERE itemid = %s AND quantity > 0
              UNION ALL
              SELECT quantity, cost_per_unit
                FROM shelf      WHERE itemid = %s AND quantity > 0
            )
            SELECT SUM(quantity * cost_per_unit) /
                   NULLIF(SUM(quantity),0) AS avg_cost
              FROM layers;
            """,
            (item_id, item_id),
        )
        avg_cost = round(
            max(float(avg_cost_df.iloc[0]["avg_cost"] or 0.0), 0.0), 2
        )

        # Unit price (prefilled with avg_cost)
        price = col_price.number_input(
            "",
            min_value=0.0,
            step=0.01,
            format="%.2f",
            value=avg_cost,
            key=f"price_{idx}",
            label_visibility="collapsed",
        )

        # Reason
        reason = col_reason.text_input(
            "",
            key=f"reason_{idx}",
            label_visibility="collapsed",
        )

        # Linked PO
        poid_sel = col_poid.selectbox(
            "",
            po_choices,
            key=f"poid_{idx}",
            label_visibility="collapsed",
        )
        poid_val = int(poid_sel) if poid_sel != "—" else None

        # Show Max Qty & Avg Cost
        col_max.markdown(f"<span style='font-size:0.8em;'>{avail_qty}</span>",
                         unsafe_allow_html=True)
        col_avg.markdown(f"<span style='font-size:0.8em;'>{avg_cost:.2f}</span>",
                         unsafe_allow_html=True)

        # Save draft line
        st.session_state.return_lines[idx] = {
            "itemid":     item_id,
            "itemname":   item_name,
            "expiredate": exp_selected,
            "quantity":   qty,
            "price":      price,
            "reason":     reason,
            "poid":       poid_val,
        }

    st.markdown("---")

    # 4) Submit whole return ───────────────────────────────────────
    with st.form("submit_return_form", clear_on_submit=True):
        credit_note = st.text_input("Supplier Credit Note (optional)")
        notes       = st.text_area("Internal Notes")

        if st.form_submit_button("📤 Submit Return"):
            payload = [
                ln for ln in st.session_state.return_lines if ln.get("quantity", 0) > 0
            ]
            if not payload:
                st.error("Enter at least one line with quantity > 0.")
                st.stop()

            total_cost = sum(ln["quantity"] * ln["price"] for ln in payload)

            ret_id = rh.create_return(
                supplier_id       = supplier_id,
                creditnote        = credit_note,
                notes             = notes,
                createdby         = st.session_state.get("user_email", "Unknown"),
                total_return_cost = total_cost,
            )
            if not ret_id:
                st.error("Database error – header not saved.")
                st.stop()

            for ln in payload:
                rh.add_return_item(
                    returnid   = ret_id,
                    itemid     = ln["itemid"],
                    quantity   = ln["quantity"],
                    itemprice  = ln["price"],
                    reason     = ln["reason"],
                    poid       = ln["poid"],
                    expiredate = ln["expiredate"],
                )

            st.success(f"✅ Return #{ret_id} saved with {len(payload)} item(s).")
            st.rerun()
