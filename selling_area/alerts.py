import streamlit as st
import pandas as pd
from datetime import date
from selling_area.shelf_handler import ShelfHandler

def alerts_tab():
    st.title("📢 Shelf Alerts")

    shelf_handler = ShelfHandler()
    
    tab1, tab2 = st.tabs(["⚠️ Low Stock Items", "⏰ Near Expiry Items"])

    # ─────────────────────────────────────────────────────────
    # TAB 1: LOW STOCK ITEMS (unchanged from your existing code)
    # ─────────────────────────────────────────────────────────
    with tab1:
        st.subheader("🚨 Global Low Stock Alerts")
        global_threshold = st.number_input(
            "🔢 Global Low Stock Threshold",
            min_value=1,
            value=10,
            step=1
        )

        low_stock_df = shelf_handler.get_low_shelf_stock(global_threshold)
        if low_stock_df.empty:
            st.success("✅ No items are below the global threshold.")
        else:
            st.warning("⚠️ Items below global threshold in selling area:")
            st.dataframe(low_stock_df, use_container_width=True, hide_index=True)

        st.markdown("---")

        st.subheader("🚨 Shelf Threshold-Based Alerts")
        shelf_qty_df = shelf_handler.get_shelf_quantity_by_item()
        if shelf_qty_df.empty:
            st.info("No items found in the selling area.")
        else:
            alerts_df = shelf_qty_df[
                (shelf_qty_df["shelfthreshold"].notna()) &
                (shelf_qty_df["shelfthreshold"] > 0) &
                (shelf_qty_df["totalquantity"] < shelf_qty_df["shelfthreshold"])
            ].copy()

            if alerts_df.empty:
                st.success("✅ All items meet or exceed their shelf threshold.")
            else:
                alerts_df["needed_for_average"] = alerts_df.apply(
                    lambda row: max(0, (row["shelfaverage"] or 0) - row["totalquantity"]),
                    axis=1
                )

                st.warning("⚠️ Items below individual shelf thresholds:")
                st.dataframe(
                    alerts_df[[
                        "itemname",
                        "totalquantity",
                        "shelfthreshold",
                        "shelfaverage",
                        "needed_for_average"
                    ]],
                    use_container_width=True,
                    hide_index=True
                )

                st.info(
                    "🔎 **Explanation**:\n"
                    "- **totalquantity**: current shelf quantity\n"
                    "- **shelfthreshold**: minimum required\n"
                    "- **shelfaverage**: desired shelf quantity\n"
                    "- **needed_for_average**: quantity needed to reach average"
                )

    # ─────────────────────────────────────────────────────────
    # TAB 2: NEAR EXPIRY ITEMS
    # Adding sub-tabs: "Days-Based" vs "Shelf-Life %"
    # ─────────────────────────────────────────────────────────
    with tab2:
        st.subheader("⏰ Near Expiry Shelf Items")

        shelf_df = shelf_handler.get_shelf_items()
        if shelf_df.empty:
            st.info("No items in the selling area.")
            return

        today = pd.to_datetime(date.today())
        shelf_df["expirationdate"] = pd.to_datetime(shelf_df["expirationdate"])
        shelf_df["days_left"] = (shelf_df["expirationdate"] - today).dt.days

        # We'll also need the shelf life from the Item table:
        # This example merges the item table (which has shelflife) into shelf_df
        item_df = shelf_handler.fetch_data("""
            SELECT itemid, shelflife
            FROM Item
        """)

        # Merge shelf_df with item_df by itemid
        shelf_df = shelf_df.merge(item_df, on="itemid", how="left")

        subtab_days, subtab_percent = st.tabs(["📅 Days-Based", "📐 Shelf Life %"])

        # ----------------------------------
        # SUBTAB A: DAYS-BASED
        # ----------------------------------
        with subtab_days:
            st.markdown("#### ⚙️ Customize Alert Thresholds (Days)")

            col_red, col_orange, col_green = st.columns(3)
            red_days = col_red.number_input("🔴 Red (≤ days)", min_value=1, value=7, step=1)
            orange_default = max(30, red_days + 1)
            orange_days = col_orange.number_input("🟠 Orange (≤ days)", min_value=red_days+1, value=orange_default, step=1)
            green_default = max(85, orange_days + 1)
            green_days = col_green.number_input("🟢 Green (≤ days)", min_value=orange_days+1, value=green_default, step=1)

            # Filter items up to green_days
            near_expiry_df = shelf_df[shelf_df["days_left"] <= green_days].copy()

            if near_expiry_df.empty:
                st.success(f"✅ No items expiring within {green_days} days.")
            else:
                def color_expiry_days(val):
                    if val <= red_days:
                        return 'background-color: red; color: white;'
                    elif val <= orange_days:
                        return 'background-color: orange;'
                    elif val <= green_days:
                        return 'background-color: green; color: white;'
                    else:
                        return ''

                display_cols = ["itemname", "quantity", "expirationdate", "days_left"]
                styled_df = near_expiry_df[display_cols].style.applymap(color_expiry_days, subset=["days_left"])

                st.warning(f"⚠️ Items expiring within {green_days} days:")
                st.write(styled_df)
                
                st.info(
                    "🔎 **Color-Coding (Days)**:\n"
                    f"- 🔴 **Red**: ≤ {red_days} days left\n"
                    f"- 🟠 **Orange**: {red_days + 1} to {orange_days} days\n"
                    f"- 🟢 **Green**: {orange_days + 1} to {green_days} days"
                )

        # ----------------------------------
        # SUBTAB B: SHELF LIFE PERCENTAGE
        # ----------------------------------
        with subtab_percent:
            st.markdown("#### ⚙️ Customize Alert Thresholds (Fraction of Shelf Life)")

            col_red_p, col_orange_p, col_green_p = st.columns(3)
            red_frac = col_red_p.number_input("🔴 Red (≤ fraction)", min_value=0.0, max_value=1.0, value=0.2, step=0.05, format="%.2f")
            orange_default_f = max(0.4, red_frac + 0.01)
            orange_frac = col_orange_p.number_input("🟠 Orange (≤ fraction)", min_value=red_frac+0.01, max_value=1.0, value=orange_default_f, step=0.05, format="%.2f")
            green_default_f = max(0.8, orange_frac + 0.01)
            green_frac = col_green_p.number_input("🟢 Green (≤ fraction)", min_value=orange_frac+0.01, max_value=1.0, value=green_default_f, step=0.05, format="%.2f")

            # We'll skip items that have no valid shelflife
            fraction_df = shelf_df[(shelf_df["shelflife"].notna()) & (shelf_df["shelflife"] > 0)].copy()
            if fraction_df.empty:
                st.info("No items have a positive shelf life defined.")
            else:
                # Compute fraction_left = days_left / shelflife
                fraction_df["fraction_left"] = fraction_df["days_left"] / fraction_df["shelflife"]

                # We'll filter up to green_frac
                # i.e., show items with fraction_left <= green_frac
                fraction_alerts_df = fraction_df[fraction_df["fraction_left"] <= green_frac].copy()

                if fraction_alerts_df.empty:
                    st.success("✅ No items are below the selected fraction of shelf life.")
                else:
                    def color_expiry_fraction(val):
                        if val <= red_frac:
                            return 'background-color: red; color: white;'
                        elif val <= orange_frac:
                            return 'background-color: orange;'
                        elif val <= green_frac:
                            return 'background-color: green; color: white;'
                        else:
                            return ''

                    display_cols_frac = ["itemname", "quantity", "expirationdate", "days_left", "shelflife", "fraction_left"]
                    styled_frac_df = fraction_alerts_df[display_cols_frac].style.applymap(
                        color_expiry_fraction, subset=["fraction_left"]
                    )

                    st.warning(f"⚠️ Items with fraction of shelf life ≤ {green_frac:.2f}:")
                    st.write(styled_frac_df)

                    st.info(
                        "🔎 **Color-Coding (Shelf Life Fraction)**:\n"
                        f"- 🔴 **Red**: ≤ {red_frac:.2f} of shelf life\n"
                        f"- 🟠 **Orange**: ({red_frac:.2f}, {orange_frac:.2f}] of shelf life\n"
                        f"- 🟢 **Green**: ({orange_frac:.2f}, {green_frac:.2f}] of shelf life\n\n"
                        "For example, if shelf life = 100 days and fraction_left = 0.2, that means only 20 days remain."
                    )

            # (Optional) Show items that are missing or have zero shelf life
            missing_shelf_life_df = shelf_df[(shelf_df["shelflife"].isna()) | (shelf_df["shelflife"] <= 0)]
            if not missing_shelf_life_df.empty:
                st.markdown("---")
                st.error("The following items have no valid shelf life, so fraction-based alerts aren't possible:")
                st.dataframe(missing_shelf_life_df[["itemname", "quantity", "expirationdate", "days_left", "shelflife"]])

