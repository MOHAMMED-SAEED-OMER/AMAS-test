# issues/main_issue.py
import streamlit as st

from .add_issue        import add_issue_tab
from .solve_issue      import solve_issue_tab
from .archived_issue   import archived_issue_tab   # ⬅ NEW

def issues_page() -> None:
    st.title("📋 Issues")

    tabs = st.tabs(
        ["➕ Report Issue", "🛠️ Open / Resolve", "📁 Archived Issues"]
    )

    with tabs[0]:
        add_issue_tab()

    with tabs[1]:
        solve_issue_tab()

    with tabs[2]:
        archived_issue_tab()
