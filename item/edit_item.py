# item/edit_item.py
import streamlit as st
import pandas as pd
from io import BytesIO
from item.item_handler import ItemHandler
import math

item_handler = ItemHandler()

NON_EDITABLE = {"itemid", "createdat", "updatedat", "itempicture"}


def _is_blank(x) -> bool:
    """True for '', None, or a pandas/NumPy NaN."""
    return x is None or (isinstance(x, float) and math.isnan(x)) or x == ""


def edit_item_tab() -> None:
    st.header("✏️ Edit Item Details")

    # 1 ─── fetch items once ────────────────────────────────────────
    items_df = item_handler.get_items()
    if items_df.empty:
        st.warning("⚠️ No items available for editing.")
        return

    # 2 ─── quick search (barcode OR name) ──────────────────────────
    search = st.text_input("🔍 Search by name *or* barcode").strip().lower()

    if search:
        mask = (
            items_df["itemnameenglish"].str.lower().str.contains(search, na=False)
            | items_df["barcode"].astype(str).str.contains(search, na=False)
        )
        items_df = items_df[mask]

    if items_df.empty:
        st.info("No match for your search.")
        return

    # build label → id map (shows barcode + name for clarity)
    item_options = {
        f"{row.barcode} · {row.itemnameenglish}": row.itemid
        for row in items_df.itertuples()
    }

    chosen_label = st.selectbox("Select an item to edit", list(item_options))
    item_id      = item_options[chosen_label]
    item_row     = items_df[items_df.itemid == item_id].iloc[0]

    # 3 ─── suppliers data ------------------------------------------
    suppliers_df   = item_handler.get_suppliers()
    supplier_names = suppliers_df.suppliername.tolist()
    linked_ids     = item_handler.get_item_suppliers(item_id)
    linked_names   = suppliers_df[suppliers_df.supplierid.isin(linked_ids)
                                 ].suppliername.tolist()

    # ─── delete section ────────────────────────────────────────────
    st.markdown("---")
    with st.expander("🗑️ Delete this item", expanded=False):
        st.warning("Deleting an item removes it from *items* and unlinks all "
                   "suppliers. Stock, sales history, etc. remain unchanged.")
        confirm = st.text_input("Type DELETE and press Enter to enable button")
        if st.button("🚨 Permanently delete item",
                     disabled=confirm.strip().upper() != "DELETE",
                     type="primary"):
            try:
                item_handler.delete_item(item_id)
                st.success(f"Item '{item_row.itemnameenglish}' deleted.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))

    # 4 ─── edit form ───────────────────────────────────────────────
    with st.form("edit_item_form"):
        st.subheader("📝 Item Fields")

        updated = {}
        for col in item_row.index:
            if col in NON_EDITABLE:
                continue

            cur_val = item_row[col]
            cur_txt = "" if pd.isna(cur_val) else str(cur_val)

            label = col.replace("_", " ").title()
            placeholder = f"(current: {cur_txt or '—'})"

            inp = st.text_input(
                f"{label} {placeholder}",
                value=cur_txt,
                key=f"edit_{col}"
            )
            updated[col] = inp

        # 4a ─── image ------------------------------------------------
        st.subheader("🖼️ Item Picture")
        if item_row.itempicture:
            st.image(BytesIO(item_row.itempicture), width=150)
        uploaded = st.file_uploader("Upload new image", type=["png", "jpg", "jpeg"])
        if uploaded:
            updated["itempicture"] = uploaded.getvalue()

        # 4b ─── suppliers -------------------------------------------
        st.subheader("🏷️ Suppliers")
        if supplier_names:
            sel_names = st.multiselect(
                "Linked suppliers",
                supplier_names,
                default=linked_names
            )
            sel_ids = suppliers_df[suppliers_df.suppliername.isin(sel_names)
                                   ].supplierid.tolist()
        else:
            sel_ids = []
            st.info("No suppliers in DB yet.")

        # ─── submit --------------------------------------------------
        if st.form_submit_button("💾 Update item"):
            # Sanitize blanks / NaNs before hitting the DB
            clean = {k: (None if _is_blank(v) else v) for k, v in updated.items()}
            item_handler.update_item(item_id, clean)
            item_handler.update_item_suppliers(item_id, sel_ids)
            st.success("✔ Item updated")
            st.rerun()
