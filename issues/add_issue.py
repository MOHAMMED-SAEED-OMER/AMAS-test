# issues/add_issue.py
import streamlit as st
from datetime import datetime
from issues.issue_handler import IssueHandler

ih = IssueHandler()


def add_issue_tab() -> None:
    st.subheader("➕  Report a new issue")

    col1, col2 = st.columns(2)
    category = col1.selectbox(
        "Category",
        ["Near-expiry", "Damaged", "Price", "cleanliness", "Other"],
    )
    location = col2.text_input("Location / aisle (optional)")
    description = st.text_area("Describe the problem", height=120)
    photo_file = st.file_uploader(
        "Attach photo (optional)", type=["jpg", "jpeg", "png"]
    )

    if st.button("Submit Issue", type="primary"):
        if not description.strip():
            st.error("Description cannot be empty.")
            st.stop()

        photo_bytes = photo_file.read() if photo_file else None
        iid = ih.add_issue(
            reported_by=st.session_state.get("user_email", "unknown@x"),
            category=category,
            location=location.strip() or None,
            description=description.strip(),
            photo_bytes=photo_bytes,
        )
        st.success(f"Issue #{iid} recorded at {datetime.now():%H:%M}.")
        st.rerun()
