import streamlit as st
# Absolute imports from the cashier package
from cashier.pos import display_pos_tab
from cashier.returns import display_return_tab
from cashier.price_check import display_price_check_tab

def main_cashier_page():
    st.title("💵 Cashier")
    # Create tabs for POS, Return Sales Bill, and Price Check
    tabs = st.tabs(["🛒 POS", "🔄 Return Sales Bill", "🔍 Price Check"])
    
    with tabs[0]:
        display_pos_tab()
    with tabs[1]:
        display_return_tab()
    with tabs[2]:
        display_price_check_tab()

if __name__ == "__main__":
    main_cashier_page()
