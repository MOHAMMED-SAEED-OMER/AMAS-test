# issues/archived_issue.py
import streamlit as st
from .issue_handler import IssueHandler

ih = IssueHandler()

def archived_issue_tab() -> None:
    st.header("📁 Archived Issues")

    # pull every non-closed issue, then keep the solved ones
    df        = ih.fetch_issues()          # returns NOT-Closed rows
    solved_df = df[df["status"] == "Solved"]

    if solved_df.empty:                    # property, not a call
        st.info("No archived issues.")
        return

    for _, row in solved_df.iterrows():
        with st.container(border=True):
            # ── basic text info ─────────────────────────────
            st.markdown(f"**Category:** {row['category']}")
            st.write(row.get("description", ""))
    
            # ── images side-by-side ─────────────────────────
            pics = []
            captions = []
            if row.photo is not None:
                pics.append(bytes(row.photo))
                captions.append("Reported")
            if row.solved_photo is not None:
                pics.append(bytes(row.solved_photo))
                captions.append("After fix")
    
            if pics:                                   # at least one picture
                cols = st.columns(len(pics))
                for col, img, cap in zip(cols, pics, captions):
                    col.image(img, caption=cap, width=240)
    
            # ── meta info ─────────────────────────────────
            st.caption(
                f"Reported {row.created_at:%Y-%m-%d %H:%M} by {row.reported_by}"
            )
            st.caption(
                f"Solved   {row.solved_at:%Y-%m-%d %H:%M} by {row.solved_by}"
            )
            if note := row.get("solved_note"):
                st.markdown(f"**Resolver note:** {note}")
