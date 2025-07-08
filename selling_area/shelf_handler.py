# selling_area/transfer.py  – barcode ➜ shelf transfer (stable, v3)
from __future__ import annotations

from typing import List, Dict, Any

import streamlit as st
import pandas as pd

from selling_area.shelf_handler import ShelfHandler

__all__ = ["transfer_tab"]

handler = ShelfHandler()

# ───────────────────────── cache helpers ──────────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def layers_for_barcode(bc: str) -> List[Dict[str, Any]]:
    """Return inventory cost-layers for a barcode as plain dictionaries."""
    return handler.get_inventory_by_barcode(bc).to_dict("records")

@st.cache_data(ttl=300, show_spinner=False)
def all_locids() -> List[str]:
    df = handler.fetch_data("SELECT locid FROM shelf_map_locations ORDER BY locid")
    return df.loc[:, "locid"].tolist() if not df.empty else []

# ───────────────────────── state helpers ──────────────────────────
def _init_row(i: int) -> None:
    """Create per-row keys the first time we reference them."""
    defaults = {
        f"bc_{i}": "",
        f"name_{i}": "",
        f"exp_{i}": "",
        f"qty_{i}": 0,
        f"loc_{i}": "",
        f"layers_{i}": [],
        f"_prevbc_{i}": "",
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

def _clear_transfer_state() -> None:
    """Purge all row keys + cached look-ups when job is done / cancelled."""
    for k in list(st.session_state.keys()):
        if k.startswith(("bc_", "name_", "exp_", "qty_", "loc_", "layers_", "_prevbc_")):
            del st.session_state[k]
    layers_for_barcode.clear()

# ───────────────────────── validation helper ──────────────────────
def _validate_rows(n_rows: int):
    errors: list[str] = []
    batch: list[Dict[str, Any]] = []

    for i in range(n_rows):
        bc   = st.session_state[f"bc_{i}"].strip()
        exp  = st.session_state[f"exp_{i}"].split(" ")[0]
        qty  = int(st.session_state[f"qty_{i}"])
        loc  = st.session_state[f"loc_{i}"].strip()
        rows = st.session_state[f"layers_{i}"]

        if not bc:
            errors.append(f"Line {i+1}: barcode missing.")
            continue
        if not exp:
            errors.append(f"Line {i+1}: expiration missing.")
            continue
        if not loc:
            errors.append(f"Line {i+1}: location missing.")
            continue

        sel_layers = [r for r in rows if str(r["expirationdate"]) == exp]
        stock      = sum(r["quantity"] for r in sel_layers)
        if qty > stock:
            errors.append(f"Line {i+1}: only {stock} available.")
            continue

        batch.append(
            {
                "itemid": sel_layers[0]["itemid"],
                "need":   qty,
                "loc":    loc,
                "layers": sel_layers,
            }
        )
    return errors, batch

# ───────────────────────── UI fragment (one grid row) ─────────────
def _draw_rows(n: int, loc_opts: List[str]) -> None:
    header = st.columns(5, gap="small")
    for col, title in zip(
        header,
        ["**Barcode**", "**Item Name**", "**Expiration**", "**Qty**", "**Location**"],
    ):
        col.markdown(title)

    for i in range(n):
        _init_row(i)
        cols = st.columns(5, gap="small")

        # --- BARCODE ---------------------------------------------------
        bc_inp = cols[0].text_input(
            key=f"bc_{i}", label=f"Barcode {i}", label_visibility="collapsed"
        ).strip()

        if bc_inp and bc_inp != st.session_state[f"_prevbc_{i}"]:
            layers = layers_for_barcode(bc_inp)
            st.session_state[f"layers_{i}"] = layers
            st.session_state[f"name_{i}"]   = layers[0]["itemname"] if layers else ""
            st.session_state[f"exp_{i}"]    = ""
            if layers and st.session_state[f"loc_{i}"] == "":
                st.session_state[f"loc_{i}"] = handler.last_locid(layers[0]["itemid"]) or ""
            st.session_state[f"_prevbc_{i}"] = bc_inp
            # qty default = total available of first cost layer
            st.session_state[f"qty_{i}"] = layers[0]["quantity"] if layers else 0

        # --- ITEM NAME (read-only) -------------------------------------
        cols[1].text_input(
            key=f"name_{i}", label=f"Name {i}",
            disabled=True, label_visibility="collapsed"
        )

        # --- EXPIRATION ------------------------------------------------
        layers = st.session_state[f"layers_{i}"]
        exp_opts = [f"{r['expirationdate']} (Qty {r['quantity']})" for r in layers]
        exp_sel  = cols[2].selectbox(
            key=f"exp_{i}", label=f"Exp {i}",
            options=[""] + exp_opts, label_visibility="collapsed"
        )

        # --- QTY --------------------------------------------------------
        exp_date    = exp_sel.split(" ")[0] if exp_sel else ""
        avail_total = sum(r["quantity"] for r in layers if str(r["expirationdate"]) == exp_date)
        current_val = st.session_state[f"qty_{i}"] or 1

        cols[3].number_input(
            key=f"qty_{i}", label=f"Qty {i}",
            min_value=1, max_value=max(avail_total, 1),
            value=min(current_val, max(avail_total, 1)),
            step=1, label_visibility="collapsed"
        )

        # --- LOCATION ---------------------------------------------------
        current_loc = st.session_state[f"loc_{i}"]
        loc_options = [""] + loc_opts if current_loc == "" else loc_opts
        cols[4].selectbox(
            key=f"loc_{i}", label=f"Loc {i}",
            options=loc_options, label_visibility="collapsed"
        )

# ───────────────────────── main tab  ───────────────────────────────
def transfer_tab() -> None:
    st.subheader("📤 Bulk Transfer (Barcode)")

    n_rows   = int(st.number_input("Lines to transfer", 1, 50, 1, 1,
                                   help="How many lines (barcodes) you want to enter"))
    loc_opts = all_locids()

    _draw_rows(n_rows, loc_opts)

    # ---------------- first click: validate & ask confirmation -------
    if "confirm_transfer" not in st.session_state:
        if st.button("🚚 Transfer All"):
            errs, batch = _validate_rows(n_rows)
            if errs:
                for e in errs:
                    st.error(e)
                return
            st.session_state["pending_transfer"] = batch
            st.session_state["confirm_transfer"] = True
            st.rerun()
        return  # stop rendering below if not yet confirming

    # ---------------- confirmation screen -----------------------------
    batch = st.session_state["pending_transfer"]
    st.markdown("### Please confirm transfer")
    for job in batch:
        st.write(f"• **Item {job['itemid']}** | Qty **{job['need']}** → Shelf **{job['loc']}**")

    ok_col, cancel_col = st.columns(2)

    # ---------- CONFIRM ------------------------------------------------
    if ok_col.button("✅ Confirm"):
        user = st.session_state.get("user_email", "Unknown")
        for job in batch:
            remaining = handler.resolve_shortages(
                itemid=job["itemid"], qty_need=job["need"], user=user
            )
            for layer in sorted(job["layers"], key=lambda r: r["cost_per_unit"]):
                if remaining == 0:
                    break
                take = min(remaining, layer["quantity"])
                handler.add_to_shelf(
                    itemid=layer["itemid"],
                    expirationdate=layer["expirationdate"],
                    quantity=take,
                    created_by=user,
                    cost_per_unit=layer["cost_per_unit"],
                    locid=job["loc"],                   # ← **now passed**
                )
                remaining -= take

        st.success("✅ Transfer completed.")
        _clear_transfer_state()
        st.session_state.pop("confirm_transfer", None)
        st.session_state.pop("pending_transfer", None)
        st.rerun()

    # ---------- CANCEL -------------------------------------------------
    if cancel_col.button("❌ Cancel"):
        _clear_transfer_state()
        st.session_state.pop("confirm_transfer", None)
        st.session_state.pop("pending_transfer", None)
        st.rerun()


if __name__ == "__main__":
    transfer_tab()
