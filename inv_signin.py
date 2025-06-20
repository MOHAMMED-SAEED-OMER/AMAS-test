# inv_signin.py
import streamlit as st
from db_handler import DatabaseManager
from auth_utils import hash_pin, verify_pin   # bcrypt helpers

db = DatabaseManager()

# ───────────────────────── helpers ────────────────────────────────
def _row_to_permissions(row):
    return {
        "CanAccessHome":        row["canaccesshome"],
        "CanAccessItems":       row["canaccessitems"],
        "CanAccessReceive":     row["canaccessreceive"],
        "CanAccessPO":          row["canaccesspo"],
        "CanAccessReports":     row["canaccessreports"],
        "CanAccessSellingArea": row["canaccesssellingarea"],
        "CanAccessCashier":     row["canaccesscashier"],
        "CanAccessFinance":     row["canaccessfinance"],
        "CanAccessReturns":     row["canaccessreturns"],
        "CanAccessIssues":      row["canaccessissues"],   # ← NEW
        "CanAccessShelfMap":    row["canaccessshelfmap"],
    }

# ───────────────────────── auth flow ──────────────────────────────
def authenticate():
    """Google SSO  ➜  mandatory PIN  ➜  permissions."""
    # 1) Google sign-in ------------------------------------------------
    if not st.user.is_logged_in:
        logo = "https://img.icons8.com/color/48/000000/google-logo.png"
        st.markdown("<h2 style='text-align:center'>Inventory Management System</h2>",
                    unsafe_allow_html=True)
        _, c, _ = st.columns([1, 3, 1])
        with c:
            st.image(logo, width=32)
            st.button("Sign in with Google", on_click=st.login, use_container_width=True)
        st.stop()

    # basic identity
    user_email = st.user.email
    user_name  = st.user.name
    st.session_state["user_email"] = user_email
    st.session_state["user_name"]  = user_name

    # 2) ensure user row exists --------------------------------------
    user_df = db.fetch_data("SELECT * FROM users WHERE email=%s", (user_email,))
    if user_df.empty:
        st.error("🚫 Your account has not been registered by an administrator.")
        st.info("Please contact your system admin to gain access.")
        st.stop()

    info     = user_df.iloc[0]
    pin_hash = info.get("pin_hash")            # may be NULL/None

    # ───────────────── PIN SET-UP (first time) ─────────────────────
    if not pin_hash:
        st.info("🔒 First-time login – please set a 4- to 8-digit PIN.")

        pin1 = st.text_input("Choose a PIN",     type="password", key="set_pin1")
        pin2 = st.text_input("Confirm your PIN", type="password", key="set_pin2")

        if st.button("Save PIN"):
            if not (pin1 and pin2):
                st.warning("Enter the PIN twice."); st.stop()
            if pin1 != pin2:
                st.error("PINs don’t match."); st.stop()
            if not (pin1.isdigit() and 4 <= len(pin1) <= 8):
                st.error("PIN must be 4–8 digits."); st.stop()

            db.execute_command(
                "UPDATE users SET pin_hash = %s WHERE email = %s",
                (hash_pin(pin1), user_email),
            )
            st.success("✔ PIN saved. Sign in again.")
            st.session_state.clear()
            st.rerun()

        st.stop()   # wait until user sets a PIN

    # 3) mandatory PIN every session --------------------------------
    if not st.session_state.get("pin_ok"):
        attempts = st.session_state.get("pin_attempts", 0)
        if attempts >= 5:
            st.error("Too many incorrect PIN attempts – refresh to try again.")
            st.stop()

        pin_try = st.text_input("Enter your PIN", type="password")
        if pin_try:
            if verify_pin(pin_try, pin_hash):
                st.session_state["pin_ok"] = True
                st.session_state.pop("pin_attempts", None)
                st.rerun()
            else:
                st.session_state["pin_attempts"] = attempts + 1
                st.error("❌ Incorrect PIN")
        st.stop()  # halt until correct PIN entered

    # 4) load permissions & role ------------------------------------
    st.session_state["permissions"] = _row_to_permissions(info)
    st.session_state["user_role"]   = info["role"]

# ───────────────────────── misc helper ────────────────────────────
def logout():
    st.logout()
