# selling_area/transfer.py  – barcode ➜ shelf transfer (bug-fixed)
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from selling_area.shelf_handler import ShelfHandler

__all__ = ["transfer_tab"]

handler = ShelfHandler()


# ───────────────────────── cached look-ups ─────────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def layers_for_barcode(bc: str) -> List[Dict[str, Any]]:
    """Return inventory cost-layers for a barcode (fresh every minute)."""
    return handler.get_inventory_by_barcode(bc).to_dict("records")


@st.cache_data(ttl=300, show_spinner=False)
def all_locids() -> List[str]:
    df = handler.fetch_data("SELECT locid FROM shelf_map_locations ORDER BY locid")
    return df["locid"].tolist() if not df.empty else []


# ───────────────────────── helpers ─────────────────────────────────
def _to_date_str(dt) -> str:
    """Return YYYY-MM-DD regardless of whether *dt* is date, datetime or str."""
    if isinstance(dt, str):
        # MySQL connector already returns 'YYYY-MM-DD' for DATE columns
        return dt.split(" ")[0]
    if isinstance(dt, (datetime, pd.Timestamp)):
        return dt.strftime("%Y-%m-%d")
    return str(dt)


def _init_row_state(i: int) -> None:
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
    errors, batch = [], []
    for i in range(n_rows):
        bc = st.session_state[f"bc_{i}"].strip()
        exp = _to_date_str(st.session_state[f"exp_{i}"].split(" ")[0])
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

        sel_layers = [l for l in lays if _to_date_str(l["expirationdate"]) == exp]
        stock = sum(l["quantity"] for l in sel_layers)
        if qty > stock:
            errors.append(f"Line {i+1}: only {stock} available.")
            continue

        batch.append(
            {
                "itemid": sel_layers[0]["itemid"],
                "need": qty,
                "loc": loc,
                "layers": sel_layers,
            }
        )
    return errors, batch


def _clear_transfer_state() -> None:
    drop_prefixes = ("bc_", "name_", "exp_", "qty_", "loc_", "layers_", "_prevbc_")
    for k in list(st.session_state.keys()):
        if k.startswith(drop_prefixes):
            del st.session_state[k]
    layers_for_barcode.clear()


# ───────────────────────── main UI ────────────────────────────────
def transfer_tab() -> None:
    st.subheader("📤 Bulk Transfer (Barcode)")

    n_rows = int(st.number_input("Lines to transfer", 1, 50, 1, 1))
    loc_opts = all_locids()

    # header
    hdr = st.columns(5, gap="small")
    for col, title in zip(
        hdr,
        ["**Barcode**", "**Item&nbsp;Name**", "**Expiration**", "**Qty**", "**Location**"],
    ):
        col.markdown(title, unsafe_allow_html=True)

    # rows
    for i in range(n_rows):
        _init_row_state(i)
        cols = st.columns(5, gap="small")

        # ── BARCODE ───────────────────────────────────────────────
        bc_key = f"bc_{i}"
        bc_val = cols[0].text_input("", key=bc_key, label_visibility="collapsed").strip()

        # barcode changed → pull fresh layers
        if bc_val and bc_val != st.session_state[f"_prevbc_{i}"]:
            layers = layers_for_barcode(bc_val)
            st.session_state[f"layers_{i}"] = layers
            st.session_state[f"name_{i}"] = layers[0]["itemname"] if layers else ""
            st.session_state[f"exp_{i}"] = ""
            if layers and st.session_state[f"loc_{i}"] == "":
                st.session_state[f"loc_{i}"] = handler.last_locid(layers[0]["itemid"]) or ""
            st.session_state[f"_prevbc_{i}"] = bc_val

        # ── NAME (read-only) ──────────────────────────────────────
        cols[1].text_input(
            "", key=f"name_{i}", disabled=True, label_visibility="collapsed"
        )

        # ── EXPIRATION SELECT ────────────────────────────────────
        layers = st.session_state[f"layers_{i}"]
        exp_opts = [f"{_to_date_str(l['expirationdate'])} (Qty {l['quantity']})" for l in layers]
        cols[2].selectbox(
            "", [""] + exp_opts, key=f"exp_{i}", label_visibility="collapsed"
        )

        # derive stock for chosen expiration
        exp_date = _to_date_str(st.session_state[f"exp_{i}"].split(" ")[0])
        avail_qty = sum(
            l["quantity"] for l in layers if _to_date_str(l["expirationdate"]) == exp_date
        )

        # ── QUANTITY ─────────────────────────────────────────────
        cols[3].number_input(
            "", key=f"qty_{i}", label_visibility="collapsed",
            min_value=1,
            max_value=max(avail_qty, 1),
            value=min(avail_qty, 1) if avail_qty else 1,
            step=1,
        )

        # ── LOCATION ─────────────────────────────────────────────
        current_loc = st.session_state[f"loc_{i}"]
        loc_choices = [""] + loc_opts if current_loc == "" else loc_opts
        cols[4].selectbox(
            "", loc_choices, key=f"loc_{i}", label_visibility="collapsed"
        )

    # ─────────────────────────────────────────────────────────────
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
    else:
        batch = st.session_state["pending_transfer"]
        st.markdown("### Please confirm transfer")
        for job in batch:
            st.write(f"• Item **{job['itemid']}** | Qty {job['need']} → Shelf {job['loc']}")

        ok_col, cancel_col = st.columns(2)

        # CONFIRM
        if ok_col.button("✅ Confirm"):
            user = st.session_state.get("user_email", "Unknown")
            for job in batch:
                left = handler.resolve_shortages(
                    itemid=job["itemid"], qty_need=job["need"], user=user
                )
                remaining = left
                # process each cost-layer cheapest first
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
                        locid=job["loc"],
                    )
                    remaining -= take

            st.success("✅ Transfer completed.")
            _clear_transfer_state()
            st.session_state.pop("confirm_transfer", None)
            st.session_state.pop("pending_transfer", None)
            st.rerun()

        # CANCEL
        if cancel_col.button("❌ Cancel"):
            _clear_transfer_state()
            st.session_state.pop("confirm_transfer", None)
            st.session_state.pop("pending_transfer", None)
            st.rerun()


if __name__ == "__main__":
    transfer_tab()
