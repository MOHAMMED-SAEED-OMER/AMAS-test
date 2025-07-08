# selling_area/transfer.py  – barcode → shelf transfer  (stable + fast)
from __future__ import annotations

from typing import List, Dict, Any
import streamlit as st
import pandas as pd

from selling_area.shelf_handler import ShelfHandler

__all__ = ["transfer_tab"]

handler = ShelfHandler()

# ────────────────── cached look-ups ──────────────────────────────
@st.cache_data(ttl=120, show_spinner=False)
def layers_for_barcode(bc: str) -> List[Dict[str, Any]]:
    """Inventory layers for one barcode (cached 2 min)."""
    return handler.get_inventory_by_barcode(bc).to_dict("records")

@st.cache_data(ttl=600, show_spinner=False)
def all_locids() -> List[str]:
    """All defined shelf locations (cached 10 min)."""
    df = handler.fetch_data("SELECT locid FROM shelf_map_locations ORDER BY locid")
    return df["locid"].tolist() if not df.empty else []

# ────────────────── helpers ──────────────────────────────────────
def _init_row_state(i: int) -> None:
    """Ensure per-row keys exist in session_state."""
    defaults = {
        f"bc_{i}": "",
        f"name_{i}": "",
        f"exp_{i}": "",
        f"qty_{i}": 1,
        f"loc_{i}": "",
        f"layers_{i}": [],
        f"_prevbc_{i}": "",
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

def _validate_rows(n_rows: int):
    """Return (errors, batch) where batch is a list of transfer jobs."""
    errors, batch = [], []
    for i in range(n_rows):
        bc  = st.session_state[f"bc_{i}"].strip()
        exp = st.session_state[f"exp_{i}"].split(" ")[0]
        qty = int(st.session_state[f"qty_{i}"])
        loc = st.session_state[f"loc_{i}"].strip()
        lays = st.session_state[f"layers_{i}"]

        if not bc:
            errors.append(f"Line {i+1}: barcode missing.")
            continue
        if not exp:
            errors.append(f"Line {i+1}: expiration missing.")
            continue
        if not loc:
            errors.append(f"Line {i+1}: location missing.")
            continue

        selected = [l for l in lays if str(l["expirationdate"]) == exp]
        stock = sum(l["quantity"] for l in selected)
        if qty > stock:
            errors.append(f"Line {i+1}: only {stock} in stock.")
            continue

        batch.append(
            {"itemid": selected[0]["itemid"], "need": qty, "loc": loc, "layers": selected}
        )
    return errors, batch

def _clear_state() -> None:
    """Remove all per-row keys and cached barcode layers."""
    for k in list(st.session_state):
        if k.startswith(("bc_", "name_", "exp_", "qty_", "loc_", "layers_", "_prevbc_")):
            del st.session_state[k]
    layers_for_barcode.clear()

# ────────────────── main tab ─────────────────────────────────────
def transfer_tab() -> None:
    st.subheader("📤 Bulk Transfer (Barcode)")

    # choose how many lines *outside* the form so users can tweak it freely
    n_rows = int(st.number_input("Lines to transfer", 1, 50, 1, 1))
    loc_opts = all_locids()

    # render all inputs inside a form → page reruns only on submit
    with st.form("transfer_form"):
        hdr = st.columns(5, gap="small")
        for col, title in zip(
            hdr,
            ["**Barcode**", "**Item&nbsp;Name**", "**Expiration**", "**Qty**", "**Location**"],
        ):
            col.markdown(title, unsafe_allow_html=True)

        for i in range(n_rows):
            _init_row_state(i)
            cols = st.columns(5, gap="small")

            # ── barcode ───────────────────────────────────────────
            bc_key = f"bc_{i}"
            bc_val = cols[0].text_input(
                label=bc_key, label_visibility="collapsed", key=bc_key
            ).strip()

            # refresh layers if barcode changed
            if bc_val and bc_val != st.session_state[f"_prevbc_{i}"]:
                layers = layers_for_barcode(bc_val)
                st.session_state[f"layers_{i}"] = layers
                st.session_state[f"name_{i}"] = layers[0]["itemname"] if layers else ""
                st.session_state[f"exp_{i}"] = ""
                if layers and st.session_state[f"loc_{i}"] == "":
                    st.session_state[f"loc_{i}"] = (
                        handler.last_locid(layers[0]["itemid"]) or ""
                    )
                st.session_state[f"_prevbc_{i}"] = bc_val

            # item name (read-only)
            cols[1].text_input(
                label=f"name_{i}", label_visibility="collapsed",
                key=f"name_{i}", disabled=True
            )

            # expiration dropdown
            layers = st.session_state[f"layers_{i}"]
            exp_opts = [f"{l['expirationdate']} (Qty {l['quantity']})" for l in layers]
            cols[2].selectbox(
                label=f"exp_{i}", label_visibility="collapsed",
                options=[""] + exp_opts, key=f"exp_{i}"
            )

            # quantity
            exp_date = st.session_state[f"exp_{i}"].split(" ")[0]
            avail_qty = sum(
                l["quantity"] for l in layers if str(l["expirationdate"]) == exp_date
            )
            cols[3].number_input(
                label=f"qty_{i}", label_visibility="collapsed",
                key=f"qty_{i}",
                min_value=1,
                max_value=max(avail_qty, 1),
                value=min(1, avail_qty) or 1,
                step=1,
            )

            # location
            current_loc = st.session_state[f"loc_{i}"]
            loc_choices = [""] + loc_opts if current_loc == "" else loc_opts
            cols[4].selectbox(
                label=f"loc_{i}", label_visibility="collapsed",
                options=loc_choices, key=f"loc_{i}"
            )

        submitted = st.form_submit_button("🚚 Transfer All")

    # first-stage validation after submit
    if submitted:
        errs, batch = _validate_rows(n_rows)
        if errs:
            for e in errs:
                st.error(e)
            return
        st.session_state["pending_transfer"] = batch
        st.session_state["confirm_transfer"] = True
        st.rerun()

    # ── confirmation step outside the form ────────────────────────
    if st.session_state.get("confirm_transfer"):
        batch = st.session_state["pending_transfer"]
        st.markdown("### Please confirm transfer")
        for job in batch:
            st.write(f"• Item **{job['itemid']}** | Qty {job['need']} → Shelf {job['loc']}")

        ok_col, cancel_col = st.columns(2)

        # confirm
        if ok_col.button("✅ Confirm"):
            user = st.session_state.get("user_email", "Unknown")
            for job in batch:
                remaining = handler.resolve_shortages(
                    itemid=job["itemid"], qty_need=job["need"], user=user
                )
                for layer in sorted(job["layers"], key=lambda l: l["cost_per_unit"]):
                    if remaining == 0:
                        break
                    take = min(remaining, layer["quantity"])
                    handler.add_to_shelf(
                        itemid=layer["itemid"],
                        expirationdate=layer["expirationdate"],
                        quantity=take,
                        created_by=user,
                        cost_per_unit=layer["cost_per_unit"],
                        locid=job["loc"],           # ← pass locid
                    )
                    remaining -= take

            st.success("✅ Transfer completed.")
            _clear_state()
            st.session_state.pop("confirm_transfer", None)
            st.session_state.pop("pending_transfer", None)
            st.rerun()

        # cancel
        if cancel_col.button("❌ Cancel"):
            _clear_state()
            st.session_state.pop("confirm_transfer", None)
            st.session_state.pop("pending_transfer", None)
            st.rerun()


if __name__ == "__main__":
    transfer_tab()
