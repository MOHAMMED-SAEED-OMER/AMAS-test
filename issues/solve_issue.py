# issues/solve_issue.py
import base64
import binascii
import io
from datetime import datetime
from typing import Union

import streamlit as st
from PIL import Image, UnidentifiedImageError  # Pillow ≥10 is already a Streamlit dep

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

    Any corrupted / non-image data is caught and shown as a warning
    instead of crashing the app.
    """
    if raw is None:
        return

    # ── Normalise to a bytes buffer ─────────────────────────────────────────
    if isinstance(raw, (bytes, memoryview)):
        data: bytes = bytes(raw)
    elif isinstance(raw, str):
        try:
            data = base64.b64decode(raw, validate=True)
        except binascii.Error:
            st.warning("⚠️ Photo field is not valid base-64 or binary data.")
            return
    else:
        st.warning(f"⚠️ Unsupported photo type: {type(raw).__name__}")
        return

    # ── Validate & display using Pillow ────────────────────────────────────
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()               # quick header check
        img = Image.open(io.BytesIO(data))  # reopen after verify()
    except (UnidentifiedImageError, OSError):
        st.warning("⚠️ Could not identify image format – is the file corrupted?")
        return

    st.image(img, width=250, caption="Reported photo")


def solve_issue_tab() -> None:
    """Streamlit tab for listing and resolving open issues."""
    st.header("🛠️ Open / Resolve Issues")

    # Fetch NOT-Closed issues; keep only rows explicitly marked "Open".
    df = ih.fetch_issues()
    open_df = df[df["status"] == "Open"]

    if open_df.empty:
        st.success("No open issues – yay!")
        return

    # Newest first for convenience
    open_df = open_df.sort_values("created_at", ascending=False)

    for _, row in open_df.iterrows():
        with st.container(border=True):
            st.markdown(f"**Category:** {row['category']}")
            st.write(row.get("description", ""))

            _display_issue_photo(row.get("photo"))

            created_at: datetime = row["created_at"]
            reporter = row.get("reported_by", "unknown")
            st.caption(f"Reported {created_at:%Y-%m-%d %H:%M} by {reporter}")
