# selling_area/alerts.py  – shelf alerts (fast & safe)
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from selling_area.shelf_handler import ShelfHandler

handler = ShelfHandler()

# ────────────────────────────────────────────────────────────────
# helpers
# ────────────────────────────────────────────────────────────────
def _rerun() -> None:
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()

@st.cache_data(ttl=180, show_spinner=False)
def load_low_stock(global_thr: int) -> pd.DataFrame:
    return handler.get_low_shelf_stock(global_thr)

@st.cache_data(ttl=180, show_spinner=False)
def load_shelf_items() -> pd.DataFrame:
    return handler.get_shelf_items()

# ────────────────────────────────────────────────────────────────
# main tab
# ────────────────────────────────────────────────────────────────
def alerts_tab() -> None:
    st.title("📢 Shelf Alerts")
    tab1, tab2 = st.tabs(["⚠️ Low Stock Items", "⏰ Near Expiry Items"])

    # ───────────────── TAB 1: Low Stock ──────────────────────────
    with tab1:
        st.subheader("🚨 Global Low Stock Alerts")
        global_thr = st.number_input("🔢 Global Low Stock Threshold", 1, value=10)
        low_stock_df = load_low_stock(global_thr)

        if low_stock_df.empty:
            st.success("✅ No items are below the global threshold.")
        else:
            st.warning("⚠️ Items below global threshold in selling area:")
            st.dataframe(low_stock_df, use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("🚨 Shelf Threshold-Based Alerts")

        shelf_qty_df = handler.get_shelf_quantity_by_item()
        if shelf_qty_df.empty:
            st.info("No items found in the selling area.")
        else:
            alerts_df = shelf_qty_df[
                (shelf_qty_df.shelfthreshold.notna()) &
                (shelf_qty_df.shelfthreshold > 0) &
                (shelf_qty_df.totalquantity < shelf_qty_df.shelfthreshold)
            ].copy()

            if alerts_df.empty:
                st.success("✅ All items meet or exceed their shelf threshold.")
            else:
                alerts_df["needed_for_average"] = (
                    alerts_df.apply(
                        lambda r: max(0, (r.shelfaverage or 0) - r.totalquantity), axis=1
                    )
                )

                st.warning("⚠️ Items below individual shelf thresholds:")
                st.dataframe(
                    alerts_df[[
                        "itemname", "totalquantity",
                        "shelfthreshold", "shelfaverage", "needed_for_average"
                    ]],
                    use_container_width=True, hide_index=True,
                )

                st.info("🔎 **Columns:** totalquantity, shelfthreshold, "
                        "shelfaverage, needed_for_average")

    # ───────────────── TAB 2: Near-Expiry ─────────────────────────
    with tab2:
        st.subheader("⏰ Near Expiry Shelf Items")

        shelf_df = load_shelf_items()
        if shelf_df.empty:
            st.info("No items in the selling area.")
            return
        if "expirationdate" not in shelf_df.columns:
            st.error("Column 'expirationdate' missing from shelf query.")
            return

        # prep columns
        today = pd.to_datetime(date.today())
        shelf_df["expirationdate"] = pd.to_datetime(shelf_df["expirationdate"])
        shelf_df["days_left"] = (shelf_df["expirationdate"] - today).dt.days

        # add shelflife from Item table
        item_df = handler.fetch_data("SELECT itemid, shelflife FROM item")
        shelf_df = shelf_df.merge(item_df, on="itemid", how="left")

        subtab_days, subtab_frac = st.tabs(["📅 Days-Based", "📐 Shelf-Life %"])

        # -------------- Days-Based -----------------
        with subtab_days:
            st.markdown("#### ⚙️ Alert thresholds (days)")
            c1, c2, c3 = st.columns(3)
            red, orange, green = (
                c1.number_input("🔴 red ≤", 1, value=7),
                c2.number_input("🟠 orange ≤", 2, value=30),
                c3.number_input("🟢 green ≤", 3, value=90),
            )
            near = shelf_df[shelf_df.days_left <= green].copy()

            if near.empty:
                st.success(f"✅ No items expiring within {green} days.")
            else:
                # colour column via gradient so Streamlit handles styling
                near["risk"] = pd.cut(
                    near.days_left,
                    bins=[-1, red, orange, green],
                    labels=["red", "orange", "green"],
                )
                st.warning(f"⚠️ Items expiring ≤ {green} days:")
                st.dataframe(
                    near[["itemname", "quantity", "expirationdate", "days_left"]],
                    use_container_width=True, hide_index=True,
                    column_config={
                        "days_left": st.column_config.NumberColumn(
                            "days_left",
                            help="Days until expiration",
                            format="%d",
                            min_value=0,
                            max_value=green,
                            color_gradient=["#ff4d4d", "#ffa500", "#63be7b"],
                        )
                    },
                )

        # -------------- Fraction-Based -------------
        with subtab_frac:
            st.markdown("#### ⚙️ Alert thresholds (fraction of shelf-life)")
            c1, c2, c3 = st.columns(3)
            red_f = c1.number_input("🔴 red ≤", 0.0, 1.0, value=0.20, step=0.05, format="%.2f")
            orange_f = c2.number_input("🟠 orange ≤", red_f + 0.01, 1.0, value=0.40, step=0.05, format="%.2f")
            green_f = c3.number_input("🟢 green ≤", orange_f + 0.01, 1.0, value=0.80, step=0.05, format="%.2f")

            valid = shelf_df[(shelf_df.shelflife.notna()) & (shelf_df.shelflife > 0)].copy()
            if valid.empty:
                st.info("No items have a positive shelf life defined.")
            else:
                valid["fraction_left"] = valid.days_left / valid.shelflife
                frac_alerts = valid[valid.fraction_left <= green_f]

                if frac_alerts.empty:
                    st.success("✅ No items below the selected fraction.")
                else:
                    frac_alerts["risk"] = pd.cut(
                        frac_alerts.fraction_left,
                        bins=[-0.01, red_f, orange_f, green_f],
                        labels=["red", "orange", "green"],
                    )
                    st.warning(f"⚠️ Items with shelf-life fraction ≤ {green_f:.2f}:")
                    st.dataframe(
                        frac_alerts[[
                            "itemname", "quantity", "expirationdate",
                            "days_left", "shelflife", "fraction_left"
                        ]],
                        use_container_width=True, hide_index=True,
                        column_config={
                            "fraction_left": st.column_config.NumberColumn(
                                "fraction_left",
                                help="Days_left / Shelf_life",
                                format="%.2f",
                                min_value=0.0,
                                max_value=green_f,
                                color_gradient=["#ff4d4d", "#ffa500", "#63be7b"],
                            )
                        },
                    )

# manual test
if __name__ == "__main__":
    alerts_tab()
