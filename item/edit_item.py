# item/edit_item.py
import streamlit as st
from io import BytesIO
from item.item_handler import ItemHandler

item_handler = ItemHandler()

NON_EDITABLE = {"itemid", "createdat", "updatedat", "itempicture"}

def edit_item_tab():
    st.header("✏️ Edit Item Details")

    # 1 ─── pick item ──────────────────────────────
    items_df = item_handler.get_items()
    if items_df.empty:
        st.warning("⚠️ No items available for editing.")
        return

    item_options = dict(zip(items_df["itemnameenglish"], items_df["itemid"]))
    chosen_name  = st.selectbox("Select an item to edit", list(item_options))
    item_id      = item_options[chosen_name]
    item_row     = items_df[items_df.itemid == item_id].iloc[0]

    suppliers_df   = item_handler.get_suppliers()
    supplier_names = suppliers_df.suppliername.tolist()
    linked_ids     = item_handler.get_item_suppliers(item_id)
    linked_names   = suppliers_df[suppliers_df.supplierid.isin(linked_ids)
                                 ].suppliername.tolist()

    # ─── delete section (moved above form) ────────
    st.markdown("---")
    with st.expander("🗑️ Delete this item", expanded=False):
        st.warning("Deleting an item removes it from *items* and unlinks all "
                   "suppliers. Stock, sales history, etc. remain unchanged.")
        confirm = st.text_input("Type DELETE and press Enter to enable button")
        disabled = confirm.strip().upper() != "DELETE"
        if st.button("🚨 Permanently delete item", disabled=disabled, type="primary"):
            try:
                item_handler.delete_item(item_id)
                st.success(f"Item '{chosen_name}' deleted.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))

    # 2 ─── edit form ──────────────────────────────
    with st.form("edit_item_form"):
        st.subheader("📝 Item Fields")

        updated = {}
        for col in item_row.index:
            if col in NON_EDITABLE: continue
            label = col.replace("_", " ").title()
            placeholder = f"(current: {item_row[col]!s})"
            updated[col] = st.text_input(
                f"{label} {placeholder}",
                value=str(item_row[col] or ""),
                key=f"edit_{col}"
            )

        st.subheader("🖼️ Item Picture")
        if item_row.itempicture:
            st.image(BytesIO(item_row.itempicture), width=150)
        uploaded = st.file_uploader("Upload new image", type=["png","jpg","jpeg"])
        if uploaded:
            updated["itempicture"] = uploaded.getvalue()

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
            sel_ids = []; st.info("No suppliers in DB yet.")

        if st.form_submit_button("💾 Update item"):
            item_handler.update_item(item_id, updated)
            item_handler.update_item_suppliers(item_id, sel_ids)
            st.success("✔ Item updated")
            st.rerun()
