# issues/solve_issue.py
import streamlit as st
from datetime import datetime
from .issue_handler import IssueHandler

__all__ = ["solve_issue_tab"]

ih = IssueHandler()

def solve_issue_tab() -> None:
    st.header("🛠️ Open / Resolve Issues")

    # get all non-closed issues then keep only those still open
    df = ih.fetch_issues()                 # ← no arg; returns NOT-Closed
    open_df = df[df["status"] == "Open"]   # only true “Open” rows

    if open_df.empty:                      # ← property, not a function
        st.success("No open issues – yay!")
        return

    for _, row in open_df.iterrows():
        with st.container(border=True):
            st.markdown(f"**Category:** {row['category']}")
            st.write(row.get("description", ""))

            # original photo
            if row.photo is not None:
                st.image(bytes(row.photo), width=250, caption="Reported photo")

            st.caption(
                f"Reported {row.created_at:%Y-%m-%d %H:%M} by {row.reported_by}"
            )
