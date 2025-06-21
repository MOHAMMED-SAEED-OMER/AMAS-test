import streamlit as st

# Existing tabs
from cashier.pos import display_pos_tab
from cashier.returns import display_return_tab
from cashier.price_check import display_price_check_tab

# NEW tab  ➜ we alias `render` to keep naming consistent
from cashier.check_out import render as display_check_out_tab


def main_cashier_page():
    st.title("💵 Cashier")

    # ───────────── tabs ─────────────
    tabs = st.tabs([
        "🛒 POS",
        "🔄 Return Sales Bill",
        "🔍 Price Check",
        "✅ Check-Out"          # ← NEW
    ])

    with tabs[0]:
        display_pos_tab()

    with tabs[1]:
        display_return_tab()

    with tabs[2]:
        display_price_check_tab()

    with tabs[3]:               # NEW
        display_check_out_tab()


if __name__ == "__main__":
    main_cashier_page()
