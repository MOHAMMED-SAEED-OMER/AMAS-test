# issues/archived_issue.py
"""
Archived / Solved Issues tab.

Fixes:
    • Prevents UnidentifiedImageError by validating each photo with Pillow.
    • Accepts bytes, memoryview, or base-64 text stored in the DB.
    • Skips any invalid / empty blobs gracefully.
"""

from __future__ import annotations

import base64
import binascii
import io
from datetime import datetime
from typing import List, Sequence, Union

import streamlit as st
from PIL import Image, UnidentifiedImageError       # Pillow ships with Streamlit

from .issue_handler import IssueHandler

ih = IssueHandler()


# ──────────────────────────────────────────────────────────────────────────────
# Helper utilities
# ──────────────────────────────────────────────────────────────────────────────
def _blob_to_image_bytes(raw: Union[bytes, memoryview, str, None]) -> bytes | None:
    """
    Normalise whatever is stored in the `photo` / `solved_photo` column:

        • bytes / memoryview          → bytes
        • base-64 encoded str         → bytes
        • anything else / invalid     → None

    Also verifies the header with Pillow so only real images pass through.
    """
    if raw is None:
        return None

    # 1️⃣  convert to bytes
    if isinstance(raw, (bytes, memoryview)):
        data = bytes(raw)
    elif isinstance(raw, str):
        try:
            data = base64.b64decode(raw, validate=True)
        except binascii.Error:
            return None
    else:
        return None

    # 2️⃣  quick header check – Pillow will raise if not an image
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()            # inexpensive header validation
    except (UnidentifiedImageError, OSError):
        return None

    return data


def _collect_photos(row) -> List[tuple[bytes, str]]:
    """
    Build a list of (image_bytes, caption) tuples for display.
    Invalid or empty blobs are silently dropped.
    """
    photos: List[tuple[bytes, str]] = []

    raw_reported = row.get("photo") or getattr(row, "photo", None)
    if (img := _blob_to_image_bytes(raw_reported)) is not None:
        photos.append((img, "Reported"))

    raw_fixed = row.get("solved_photo") or getattr(row, "solved_photo", None)
    if (img := _blob_to_image_bytes(raw_fixed)) is not None:
        photos.append((img, "After fix"))

    return photos


# ──────────────────────────────────────────────────────────────────────────────
# Main tab
# ──────────────────────────────────────────────────────────────────────────────
def archived_issue_tab() -> None:
    """Render the *Archived / Solved Issues* page."""
    st.header("📁 Archived Issues")

    # Fetch NOT-Closed issues (handler default) and keep only the Solved ones
    df = ih.fetch_issues()
    solved_df = df[df["status"] == "Solved"]

    if solved_df.empty:
        st.info("No archived issues.")
        return

    # Newest first
    solved_df = solved_df.sort_values("solved_at", ascending=False)

    for _, row in solved_df.iterrows():
        with st.container(border=True):
            # ── text info ────────────────────────────────────────────────
            st.markdown(f"**Category:** {row['category']}")
            st.write(row.get("description", ""))

            # ── images side-by-side (validated) ─────────────────────────
            photos = _collect_photos(row)
            if photos:
                cols = st.columns(len(photos))
                for col, (img_bytes, cap) in zip(cols, photos, strict=False):
                    col.image(img_bytes, caption=cap, width=240)

            # ── meta info ───────────────────────────────────────────────
            created_at: datetime = row["created_at"]
            solved_at:   datetime = row["solved_at"]

            st.caption(
                f"Reported {created_at:%Y-%m-%d %H:%M} by {row.get('reported_by', 'unknown')}"
            )
            st.caption(
                f"Solved   {solved_at:%Y-%m-%d %H:%M} by {row.get('solved_by', 'unknown')}"
            )

            if note := row.get("solved_note"):
                st.markdown(f"**Resolver note:** {note}")
