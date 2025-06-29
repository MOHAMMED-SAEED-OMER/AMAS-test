# ── receive_items/receive_items.py ────────────────────────────────────
from datetime import date
import streamlit as st
from receive_items.receive_handler import ReceiveHandler

rh = ReceiveHandler()          # DB helper


# ────────────────────────── helpers ───────────────────────────────────
def _init_row_state(idx: int):
    for k, v in {
        f"bc_{idx}":   "",
        f"name_{idx}": "",
        f"exp_{idx}":  date.today(),
        f"qty_{idx}":  1,
        f"cst_{idx}":  0.00,
        f"loc_{idx}":  "",
        f"note_{idx}": "",
    }.items():
        st.session_state.setdefault(k, v)


# ─────────────────────────── FRAGMENT ────────────────────────────────
@st.fragment
def receipt_rows_fragment(n_rows: int, bc_to_item: dict) -> None:
    """Compact rows: single header + tight spacing (Streamlit ≥ 1.46)."""

    # Inject CSS **once** to trim vertical padding around widgets
    if "compact_css" not in st.session_state:
        st.markdown(
            """
            <style>
            /* remove extra bottom-margin that Streamlit puts after columns */
            div[data-testid="stHorizontalBlock"] { margin-bottom: 2px; }

            /* tighten padding inside each column cell */
            div[data-testid="column"] > div:first-child { padding-top: 1px; padding-bottom: 1px; }
            </style>
            """,
            unsafe_allow_html=True,
        )
        st.session_state["compact_css"] = True

    # Header row
    hdr = st.columns(7, gap="small")
    for col, title in zip(
        hdr,
        ["**Barcode**", "**Item&nbsp;Name**", "**Exp&nbsp;Date**", "**Qty**",
         "**Cost/Unit**", "**Location**", "**Note**"],
    ):
        col.markdown(title, unsafe_allow_html=True)

    # Data rows (labels collapsed, gap="small" keeps them snug)
    for idx in range(n_rows):
        _init_row_state(idx)

        cols = st.columns(7, gap="small")

        bc_key = f"bc_{idx}"
        bc_val = cols[0].text_input(
            "Barcode", key=bc_key, label_visibility="collapsed"
        )

        name_key = f"name_{idx}"
        st.session_state[name_key] = bc_to_item.get(bc_val.strip(), ("", ""))[1]
        cols[1].text_input(
            "Item Name", key=name_key, disabled=True, label_visibility="collapsed"
        )

        cols[2].date_input(
            "Exp Date", key=f"exp_{idx}", value=st.session_state[f"exp_{idx}"],
            label_visibility="collapsed"
        )
        cols[3].number_input(
            "Qty", min_value=1, step=1, key=f"qty_{idx}",
            label_visibility="collapsed"
        )
        cols[4].number_input(
            "Cost / Unit", min_value=0.0, step=0.01, format="%.2f",
            key=f"cst_{idx}", label_visibility="collapsed"
        )
        cols[5].text_input(
            "Location", key=f"loc_{idx}", label_visibility="collapsed"
        )
        cols[6].text_input(
            "Note", key=f"note_{idx}", label_visibility="collapsed"
        )

# ─────────────────────────── PAGE ────────────────────────────────────
def receive_items() -> None:
    st.header("➕ Manual Stock Receipt")

    # Supplier picker
    supp_df = rh.get_suppliers()
    if supp_df.empty:                     # ← FIX
        st.warning("⚠️ Add suppliers first.")
        return
    supp_map = dict(zip(supp_df.suppliername, supp_df.supplierid))
    supplier_name = st.selectbox("Supplier", list(supp_map.keys()))
    supplier_id   = supp_map[supplier_name]

    # How many rows?
    n_lines = st.number_input("How many different items are arriving?",
                              min_value=1, step=1, format="%d")

    # Catalogue lookup
    items_df = rh.fetch_data("SELECT itemid, barcode, itemnameenglish FROM item")
    if items_df.empty:                    # already correct
        st.warning("⚠️ Add items first.")
        return
    bc_to_item = {row.barcode: (row.itemid, row.itemnameenglish)
                  for row in items_df.itertuples(index=False)}

    st.subheader("Receipt lines")
    receipt_rows_fragment(n_lines, bc_to_item)

    # Commit button
    if st.button("✅ Receive Items"):
        inv_rows = []
        for idx in range(n_lines):
            bc = st.session_state[f"bc_{idx}"].strip()
            if bc == "":
                st.error(f"Line {idx+1}: barcode is required.")
                return
            lookup = bc_to_item.get(bc)
            if lookup is None:
                st.error(f"Line {idx+1}: unknown barcode “{bc}”.")
                return

            item_id, item_name = lookup
            inv_rows.append({
                "item_id":          item_id,
                "name":             item_name,
                "quantity":         int(st.session_state[f"qty_{idx}"]),
                "expiration_date":  st.session_state[f"exp_{idx}"],
                "cost_per_unit":    float(st.session_state[f"cst_{idx}"]),
                "storage_location": st.session_state[f"loc_{idx}"].strip(),
                "note":             st.session_state[f"note_{idx}"].strip(),
            })

        poid = rh.create_manual_po(supplier_id, note="")
        batch_inv = []
        for ln in inv_rows:
            rh.add_po_item(poid, ln["item_id"], ln["quantity"], ln["cost_per_unit"])
            costid = rh.insert_poitem_cost(
                poid, ln["item_id"], ln["cost_per_unit"],
                ln["quantity"], ln["note"]
            )
            batch_inv.append({
                "item_id":          ln["item_id"],
                "quantity":         ln["quantity"],
                "expiration_date":  ln["expiration_date"],
                "storage_location": ln["storage_location"],
                "cost_per_unit":    ln["cost_per_unit"],
                "poid":             poid,
                "costid":           costid,
            })

        rh.add_items_to_inventory(batch_inv)
        rh.refresh_po_total_cost(poid)

        st.success(f"📦 Recorded {len(batch_inv)} lines for supplier "
                   f"**{supplier_name}**. Synthetic PO #{poid} created.")

        # Reset state
        for idx in range(n_lines):
            for suffix in ("bc", "name", "exp", "qty", "cst", "loc", "note"):
                st.session_state.pop(f"{suffix}_{idx}", None)
        st.rerun()


if __name__ == "__main__":
    receive_items()
