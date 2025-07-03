# admin/add_users.py
import streamlit as st
from db_handler import DatabaseManager
from auth_utils import hash_pin
import os
from datetime import datetime
import re

# ────────────────────────── fetch dynamic permission columns ──────────────────────────
@st.cache_data(ttl=600)
def _discover_perm_cols() -> list[str]:
    db = DatabaseManager()
    q = """
      SELECT column_name
      FROM   information_schema.columns
      WHERE  table_name = 'users' AND column_name ILIKE 'canaccess%'
      ORDER  BY column_name;
    """
    try:
        return db.fetch_data(q)["column_name"].tolist()
    except Exception:
        return [
            "canaccesshome", "canaccessitems", "canaccessreceive",
            "canaccesspo", "canaccessreports", "canaccesssellingarea",
            "canaccesscashier", "canaccessfinance", "canaccessreturns",
            "canaccessshelfmap", "canaccessissues"
        ]

PERM_COLS = _discover_perm_cols()
_pretty   = lambda c: c.replace("canaccess", "").title()

# ────────────────────────── Add User Form ──────────────────────────
def add_user_tab() -> None:
    st.title("➕ Add New User")

    with st.form("add_user_form"):
        st.subheader("🧍 Personal Information")
        name  = st.text_input("Full Name", max_chars=255)
        email = st.text_input("Email Address")
        role  = st.selectbox("Role", ["User", "Admin"], index=0)
        photo = st.file_uploader("Upload Profile Photo (optional)", type=["jpg", "jpeg", "png"])

        st.subheader("🔐 Set Initial PIN")
        pin = st.text_input("Initial PIN (4–8 digits)", type="password")

        st.subheader("📄 Page Access Permissions")
        cols = st.columns(3)
        permissions = {
            col: cols[i % 3].checkbox(_pretty(col))
            for i, col in enumerate(PERM_COLS)
        }

        submitted = st.form_submit_button("✅ Create User")

    if submitted:
        if not (name and email and pin):
            st.warning("Please fill in all required fields.")
            return

        if not (pin.isdigit() and 4 <= len(pin) <= 8):
            st.error("PIN must be 4–8 digits long and numeric.")
            return

        db = DatabaseManager()

        # ───── Check if user already exists ─────────────
        check = db.fetch_data("SELECT 1 FROM users WHERE email = %s", (email,))
        if not check.empty:
            st.error("A user with this email already exists.")
            return

        # ───── Save uploaded photo if any ─────────────
        photo_url = None
        if photo:
            # ── Validate uploaded file ──
            allowed_types = {"image/png", "image/jpeg"}
            max_size = 5 * 1024 * 1024  # 5 MB

            if photo.type not in allowed_types:
                st.error("Invalid image type. Please upload PNG or JPEG files only.")
                return

            photo_bytes = photo.getvalue()
            if len(photo_bytes) > max_size:
                st.error("Image file is too large (max 5 MB).")
                return

            os.makedirs("photos", exist_ok=True)
            safe_email = re.sub(r"[^a-zA-Z0-9_.@-]", "_", email)
            filename = f"{safe_email.replace('@', '_at_')}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.png"
            filepath = os.path.join("photos", filename)
            with open(filepath, "wb") as f:
                f.write(photo_bytes)
            photo_url = filepath

        # ───── Insert user into the database ────────────
        db.execute_command(
            f"""
            INSERT INTO users (
                name, email, role, pin_hash, photo_url,
                {", ".join(permissions.keys())}
            ) VALUES (
                %s, %s, %s, %s, %s,
                {", ".join(["%s"] * len(permissions))}
            )
            """,
            (name, email, role, hash_pin(pin), photo_url, *permissions.values())
        )

        # ───── Audit logging ─────────────
        db.execute_command(
            """
            INSERT INTO audit_log (admin_email, action, target_email, description)
            VALUES (%s, %s, %s, %s)
            """,
            (
                st.session_state.get("user_email", "unknown"),
                "CREATE_USER",
                email,
                f"Added user '{name}' with role '{role}' and photo: {bool(photo_url)}"
            )
        )

        st.success(f"✅ User '{name}' has been added successfully.")
