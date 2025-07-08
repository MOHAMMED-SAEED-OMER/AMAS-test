# selling_area/alerts.py  – shelf alerts (crash-safe)
from __future__ import annotations

from datetime import date
import pandas as pd
import streamlit as st
from selling_area.shelf_handler import ShelfHandler

handler = ShelfHandler()

# ─── helpers ───────────────────────────────────────────────────────
@st.cache_data(ttl=180, show_spinner=False)
def load_low_stock(thr: int) -> pd.DataFrame:
    return handler.get_low_shelf_stock(thr)

@st.cache_data(ttl=180, show_spinner=False)
def load_shelf_items() -> pd.DataFrame:
    return handler.get_shelf_items()

# ─── main tab ──────────────────────────────────────────────────────
def alerts_tab() -> None:
    st.title("📢 Shelf Alerts")
    tab1, tab2 = st.tabs(["⚠️ Low Stock Items", "⏰ Near Expiry Items"])

    # ── TAB 1 : Low stock ───────────────────────────────────────────
    with tab1:
        st.subheader("🚨 Global Low Stock Alerts")
        thr = st.number_input("🔢 Global Low Stock Threshold", 1, value=10)
        low_df = load_low_stock(thr)

        if low_df.empty:
            st.success("✅ No items are below the global threshold.")
        else:
            st.warning("⚠️ Items below global threshold in selling area:")
            st.dataframe(low_df, use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("🚨 Shelf Threshold-Based Alerts")
        qty_df = handler.get_shelf_quantity_by_item()

        if qty_df.empty:
            st.info("No items found in the selling area.")
        else:
            al_df = qty_df[
                (qty_df.shelfthreshold.notna()) &
                (qty_df.shelfthreshold > 0) &
                (qty_df.totalquantity < qty_df.shelfthreshold)
            ].copy()

            if al_df.empty:
                st.success("✅ All items meet or exceed their shelf threshold.")
            else:
                al_df["needed_for_average"] = al_df.apply(
                    lambda r: max(0, (r.shelfaverage or 0) - r.totalquantity), axis=1
                )
                st.warning("⚠️ Items below individual shelf thresholds:")
                st.dataframe(
                    al_df[[
                        "itemname", "totalquantity",
                        "shelfthreshold", "shelfaverage", "needed_for_average"
                    ]],
                    use_container_width=True, hide_index=True,
                )

    # ── TAB 2 : Near-expiry ────────────────────────────────────────
    with tab2:
        st.subheader("⏰ Near Expiry Shelf Items")

        shelf_df = load_shelf_items()
        if shelf_df.empty:
            st.info("No items in the selling area.")
            return
        if "expirationdate" not in shelf_df.columns:
            st.error("Column 'expirationdate' missing from shelf query.")
            return

        today = pd.to_datetime(date.today())
        shelf_df["expirationdate"] = pd.to_datetime(shelf_df["expirationdate"])
        shelf_df["days_left"] = (shelf_df["expirationdate"] - today).dt.days

        item_df = handler.fetch_data("SELECT itemid, shelflife FROM item")
        shelf_df = shelf_df.merge(item_df, on="itemid", how="left")

        sub_days, sub_frac = st.tabs(["📅 Days-Based", "📐 Shelf-Life %"])

        # ---- Days-based view ----
        with sub_days:
            c1, c2, c3 = st.columns(3)
            red, orange, green = (
                c1.number_input("🔴 red ≤ (days)", 1, value=7),
                c2.number_input("🟠 orange ≤ (days)", 2, value=30),
                c3.number_input("🟢 green ≤ (days)", 3, value=90),
            )
            near = shelf_df[shelf_df.days_left <= green]

            if near.empty:
                st.success(f"✅ No items expiring within {green} days.")
            else:
                st.warning(f"⚠️ Items expiring ≤ {green} days:")
                st.dataframe(
                    near[["itemname", "quantity", "expirationdate", "days_left"]],
                    use_container_width=True, hide_index=True,
                )

        # ---- Fraction-based view ----
        with sub_frac:
            c1, c2, c3 = st.columns(3)
            red_f  = c1.number_input("🔴 red ≤ fraction", 0.0, 1.0, 0.20, 0.05, format="%.2f")
            org_f  = c2.number_input("🟠 orange ≤ fraction", red_f + 0.01, 1.0, 0.40, 0.05, format="%.2f")
            grn_f  = c3.number_input("🟢 green ≤ fraction", org_f + 0.01, 1.0, 0.80, 0.05, format="%.2f")

            valid = shelf_df[(shelf_df.shelflife.notna()) & (shelf_df.shelflife > 0)].copy()
            if valid.empty:
                st.info("No items have a positive shelf life defined.")
            else:
                valid["fraction_left"] = valid.days_left / valid.shelflife
                frac_alerts = valid[valid.fraction_left <= grn_f]

                if frac_alerts.empty:
                    st.success("✅ No items below the selected fraction.")
                else:
                    st.warning(f"⚠️ Items with shelf-life fraction ≤ {grn_f:.2f}:")
                    st.dataframe(
                        frac_alerts[[
                            "itemname", "quantity", "expirationdate",
                            "days_left", "shelflife", "fraction_left"
                        ]],
                        use_container_width=True, hide_index=True,
                    )

# manual run
if __name__ == "__main__":
    alerts_tab()
