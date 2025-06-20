# finance/main_finance.py
import streamlit as st

from finance.supplier_debts import supplier_debts_tab
from finance.sup_payment    import sup_payment_tab
from finance.item_profit    import profit_tab as item_profit_tab   # alias
from finance.salary         import salary_tab


def main_finance_page():
    """Top‑level Finance dashboard with four feature tabs."""
    st.title("💰 Finance")

    tabs = st.tabs([
        "📑 Supplier Debts",
        "💵 Supplier Payments",
        "📈 Item Profit",
        "🧾 Employee Salaries",
    ])

    with tabs[0]:
        supplier_debts_tab()

    with tabs[1]:
        sup_payment_tab()

    with tabs[2]:
        item_profit_tab()

    with tabs[3]:
        salary_tab()


# standalone test
if __name__ == "__main__":
    main_finance_page()
