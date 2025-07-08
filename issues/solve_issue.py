# issues/solve_issue.py
import base64
import binascii
import imghdr
from datetime import datetime
from typing import Union

import streamlit as st

from .issue_handler import IssueHandler

__all__ = ["solve_issue_tab"]

ih = IssueHandler()


def _display_issue_photo(raw: Union[bytes, memoryview, str, None]) -> None:
    """
    Safely display an image stored in the `photo` column.

    Accepts:
        • bytes / memoryview containing a valid image
        • base-64 encoded str
        • None (nothing happens)

    If the data is not a recognisable image, shows a warning instead of raising.
    """
    if raw is None:
        return

    # ── Normalise to a `bytes` buffer ──────────────────────────────────
    if isinstance(raw, (bytes, memoryview)):
        data: bytes = bytes(raw)
    elif isinstance(raw, str):
        try:
            # psycopg automatically decodes BYTEA to str in "hex" mode if
            # bytea_output = 'hex'. But most people store base-64 in text.
            data = base64.b64decode(raw, validate=True)
        except binascii.Error:
            st.warning("⚠️ Photo field is not valid base-64 or binary data.")
            return
    else:
        st.warning(f"⚠️ Unsupported photo type: {type(raw).__name__}")
        return

    # ── Validate the image header before calling st.image ──────────────
    if imghdr.what(None, h=data) is None:
        st.warning("⚠️ Could not identify image format – is the file corrupted?")
        return

    st.image(data, width=250, caption="Reported photo")


def solve_issue_tab() -> None:
    """Streamlit tab for listing and resolving open issues."""
    st.header("🛠️ Open / Resolve Issues")

    # Fetch NOT-Closed issues; keep only rows explicitly marked "Open".
    df = ih.fetch_issues()
    open_df = df[df["status"] == "Open"]

    if open_df.empty:
        st.success("No open issues – yay!")
        return

    # Iterate deterministically – newest first
    open_df = open_df.sort_values("created_at", ascending=False)

    for _, row in open_df.iterrows():
        with st.container(border=True):
            st.markdown(f"**Category:** {row['category']}")
            st.write(row.get("description", ""))

            # Display attached photo safely
            _display_issue_photo(row.get("photo"))

            # Footer
            created_at: datetime = row["created_at"]
            reporter = row.get("reported_by", "unknown")
            st.caption(f"Reported {created_at:%Y-%m-%d %H:%M} by {reporter}")
