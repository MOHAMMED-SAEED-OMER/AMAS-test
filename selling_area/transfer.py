# ── selling_area/transfer.py ─────────────────────────────────────────
from datetime import date
from typing import List, Dict, Any

import pandas as pd
import streamlit as st
from db_handler import DatabaseManager


# ────────────────────── DB helper ────────────────────────────────────
class BarcodeShelfHandler(DatabaseManager):
    """Helpers for inventory → shelf transfers driven by barcodes."""

    # -----------------------------------------------------------------
    # Inventory look-ups
    # -----------------------------------------------------------------
    def get_layers(self, barcode: str) -> pd.DataFrame:
        return self.fetch_data(
            """
            SELECT inv.itemid,
                   i.itemnameenglish AS itemname,
                   inv.expirationdate,
                   inv.quantity      AS qty,
                   inv.cost_per_unit AS cost
            FROM   inventory inv
            JOIN   item       i ON inv.itemid = i.itemid
            WHERE  i.barcode = %s
              AND  inv.quantity > 0
            ORDER  BY inv.expirationdate, inv.cost_per_unit
            """,
            (barcode,),
        )

    def last_locid(self, itemid: int) -> str | None:
        df = self.fetch_data(
            """
            SELECT locid
              FROM shelfentries
             WHERE itemid = %s
               AND locid  IS NOT NULL
          ORDER BY entrydate DESC
             LIMIT 1
            """,
            (itemid,),
        )
        return None if df.empty else str(df.iloc[0, 0])

    # -----------------------------------------------------------------
    # Shortage resolver (cashier-logged shortages)
    # -----------------------------------------------------------------
    def resolve_shortages(self, *, itemid: int, qty_need: int, user: str) -> int:
        rows = self.fetch_data(
            """
            SELECT shortageid, shortage_qty
              FROM shelf_shortage
             WHERE itemid  = %s
               AND resolved = FALSE
          ORDER BY logged_at
            """,
            (itemid,),
        )

        remaining = qty_need
        for r in rows.itertuples():
            if remaining == 0:
                break

            take = min(remaining, int(r.shortage_qty))

            if take == r.shortage_qty:  # fully resolve this row
                self.execute_command(
                    "DELETE FROM shelf_shortage WHERE shortageid = %s", (r.shortageid,)
                )
            else:  # partial resolution
                self.execute_command(
                    """
                    UPDATE shelf_shortage
                       SET shortage_qty = shortage_qty - %s,
                           resolved_qty  = COALESCE(resolved_qty,0) + %s,
                           resolved_by   = %s,
                           resolved_at   = CURRENT_TIMESTAMP
                     WHERE shortageid   = %s
                    """,
                    (take, take, user, r.shortageid),
                )

            remaining -= take

        return remaining  # qty still to place on shelf

    # -----------------------------------------------------------------
    # MOVE a cost layer from Inventory → Shelf
    # -----------------------------------------------------------------
    def move_layer(self, *, itemid, expiration, qty, cost, locid, by):
        """Deduct one layer from inventory and upsert it into the shelf table."""
        # 1) reduce that exact layer in inventory
        self.execute_command(
            """
            UPDATE inventory
               SET quantity = quantity - %s
             WHERE itemid         = %s
               AND expirationdate = %s
               AND cost_per_unit  = %s
               AND quantity       >= %s
            """,
            (qty, itemid, expiration, cost, qty),
        )

        # 2) upsert into shelf  (MySQL-8 safe syntax: alias the VALUES row)
        self.execute_command(
            """
            INSERT INTO shelf (itemid, expirationdate, quantity, cost_per_unit, locid)
            VALUES (%s, %s, %s, %s, %s) AS new
            ON DUPLICATE KEY UPDATE
                quantity    = shelf.quantity + new.quantity,
                cost_per_unit = new.cost_per_unit,
                lastupdated = CURRENT_TIMESTAMP
            """,
            (itemid, expiration, qty, cost, locid),
        )

        # 3) movement log
        self.execute_command(
            """
            INSERT INTO shelfentries (itemid, expirationdate, quantity, createdby, locid)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (itemid, expiration, qty, by, locid),
        )


handler = BarcodeShelfHandler()

# ────────────── cached helpers ───────────────────────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def layers_for_barcode(bc: str) -> List[Dict[str, Any]]:
    return handler.get_layers(bc).to_dict("records")


@st.cache_data(ttl=300, show_spinner=False)
def all_locids() -> List[str]:
    df = handler.fetch_data("SELECT locid FROM shelf_map_locations ORDER BY locid")
    return df["locid"].tolist() if not df.empty else []


# ─────────────── UI helpers (css, init) ──────────────────────────────
def _css_once():
    if "_xfer_css" not in st.session_state:
        st.markdown(
            """
            <style>
            div[data-testid='stHorizontalBlock'] { margin-bottom: 2px; }
            div[data-testid='column'] > div:first-child { padding: 1px 0; }
            </style>
            """,
            unsafe_allow_html=True,
        )
        st.session_state["_xfer_css"] = True


def _init_row(i: int):
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


# ─────────────── rows fragment ───────────────────────────────────────
@st.fragment
def rows(n: int):
    _css_once()
    hdr = st.columns(5, gap="small")
    for col, title in zip(
        hdr,
        ["**Barcode**", "**Item&nbsp;Name**", "**Expiration**", "**Qty**", "**Location**"],
    ):
        col.markdown(title, unsafe_allow_html=True)

    loc_opts = all_locids()

    for i in range(n):
        _init_row(i)
        cols = st.columns(5, gap="small")

        # ── barcode ---------------------------------------------------
        bc_val = cols[0].text_input("", key=f"bc_{i}", label_visibility="collapsed").strip()

        # barcode changed → refresh layers
        if bc_val and bc_val != st.session_state[f"_prevbc_{i}"]:
            layers = layers_for_barcode(bc_val)
            st.session_state[f"layers_{i}"] = layers
            st.session_state[f"name_{i}"] = layers[0]["itemname"] if layers else ""
            st.session_state[f"exp_{i}"] = ""
            if layers and st.session_state[f"loc_{i}"] == "":
                st.session_state[f"loc_{i}"] = handler.last_locid(layers[0]["itemid"]) or ""
            st.session_state[f"_prevbc_{i}"] = bc_val

        # item name (read-only)
        cols[1].text_input("", key=f"name_{i}", disabled=True, label_visibility="collapsed")

        # expiration dropdown
        layers = st.session_state[f"layers_{i}"]
        exp_opts = [f"{l['expirationdate']} (Qty {l['qty']})" for l in layers]
        exp_sel = cols[2].selectbox(
            "", [""] + exp_opts, key=f"exp_{i}", label_visibility="collapsed"
        )
        exp_date = exp_sel.split(" ")[0] if exp_sel else ""
        avail_qty = sum(l["qty"] for l in layers if str(l["expirationdate"]) == exp_date)

        # quantity
        cols[3].number_input(
            "", key=f"qty_{i}",
            min_value=1, max_value=max(avail_qty, 1),
            value=min(1, avail_qty) or 1, step=1,
            label_visibility="collapsed",
        )

        # location dropdown
        current_loc = st.session_state[f"loc_{i}"]
        loc_choices = [""] + loc_opts if current_loc == "" else loc_opts
        cols[4].selectbox(
            "", loc_choices, key=f"loc_{i}", label_visibility="collapsed"
        )


# ─────────────── validation helper ───────────────────────────────────
def _validate(n_rows: int):
    errors, batch = [], []
    for i in range(n_rows):
        bc = st.session_state[f"bc_{i}"].strip()
        exp = st.session_state[f"exp_{i}"].split(" ")[0]
        qty = int(st.session_state[f"qty_{i}"])
        loc = st.session_state[f"loc_{i}"].strip()
        lays = st.session_state[f"layers_{i}"]

        if not bc:
            errors.append(f"Line {i + 1}: barcode missing.")
            continue
        if not exp:
            errors.append(f"Line {i + 1}: expiration missing.")
            continue
        if not loc:
            errors.append(f"Line {i + 1}: location missing.")
            continue

        sel_layers = [l for l in lays if str(l["expirationdate"]) == exp]
        stock = sum(l["qty"] for l in sel_layers)
        if qty > stock:
            errors.append(f"Line {i + 1}: only {stock} available.")
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


# ─────────────── main tab ────────────────────────────────────────────
def transfer_tab():
    st.subheader("📤 Bulk Transfer (Barcode)")

    n_rows = st.number_input("Lines to transfer", 1, 50, 1, 1)
    rows(n_rows)

    confirming = st.session_state.get("confirm_transfer", False)

    if not confirming:
        if st.button("🚚 Transfer All"):
            errs, batch = _validate(n_rows)
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

        # ------- CONFIRM -------
        if ok_col.button("✅ Confirm"):
            user = st.session_state.get("user_email", "Unknown")

            for job in batch:
                left = job["need"]

                # 1) compensate shortages
                left = handler.resolve_shortages(
                    itemid=job["itemid"], qty_need=left, user=user
                )

                # 2) place remainder on shelf
                remaining = left
                for layer in sorted(job["layers"], key=lambda l: l["cost"]):
                    if remaining == 0:
                        break
                    take = min(remaining, layer["qty"])
                    handler.move_layer(
                        itemid=layer["itemid"],
                        expiration=layer["expirationdate"],
                        qty=take,
                        cost=layer["cost"],
                        locid=job["loc"],
                        by=user,
                    )
                    remaining -= take

            st.success("✅ Transfer completed.")

            # clear session/cache
            for k in list(st.session_state.keys()):
                if k.startswith(
                    ("bc_", "name_", "exp_", "qty_", "loc_", "layers_", "_prevbc_")
                ):
                    del st.session_state[k]
            layers_for_barcode.clear()

            st.session_state.pop("confirm_transfer", None)
            st.session_state.pop("pending_transfer", None)
            st.rerun()

        # ------- CANCEL -------
        if cancel_col.button("❌ Cancel"):
            st.session_state.pop("confirm_transfer", None)
            st.session_state.pop("pending_transfer", None)
            st.rerun()


if __name__ == "__main__":
    transfer_tab()
