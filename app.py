# app.py ────────────────────────────────────────────────────────────────────
import streamlit as st
st.set_page_config(page_title="Inventory Management System", layout="wide")

# ── Page modules (unchanged) ───────────────────────────────────────────────
import home
from item                       import mainitem
import PO.mainpo                as mainpo
from receive_items.main_receive import main_receive_page
import reports.main_reports      as main_reports
from selling_area.main_shelf     import main_shelf_page
from cashier.main_cashier        import main_cashier_page
from finance.main_finance        import main_finance_page
from returns.main_return         import main_return_page
from issues.main_issue           import issues_page
from shelf_map.main_map          import main as shelf_map_page

# helpers
from inv_signin  import authenticate
from admin.user_admin_tabs import show_user_admin

# ───────────────────────────  PAGE CONFIG  ────────────────────────────────
PAGES = [
    ("Home",           "🏠", "CanAccessHome",        home.home),
    ("Item",           "📦", "CanAccessItems",       mainitem.item_page),
    ("Receive Items",  "📥", "CanAccessReceive",     main_receive_page),
    ("Purchase Order", "🧾", "CanAccessPO",          mainpo.po_page),
    ("Selling Area",   "🛒", "CanAccessSellingArea", main_shelf_page),
    ("Cashier",        "💵", "CanAccessCashier",     main_cashier_page),
    ("Finance",        "💰", "CanAccessFinance",     main_finance_page),
    ("Returns",        "↩️", "CanAccessReturns",     main_return_page),
    ("Issues",         "🐞", "CanAccessIssues",      issues_page),
    ("Shelf Map",      "🗺️", "CanAccessShelfMap",   shelf_map_page),
    ("Reports",        "📊", "CanAccessReports",     main_reports.reports_page),
    ("User Management","🛠️", "ROLE_ADMIN",          show_user_admin),
    ("Assets",         "💼", None, lambda: st.info("Assets page WIP")),
    ("Supplier",       "🚚", None, lambda: st.info("Supplier page WIP")),
]

# ───────────────────────────  UTILS  ───────────────────────────────────────
def _safe_rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    elif hasattr(st, "experimental_rerun"):
        st.experimental_rerun()
    else:  # fallback
        st.experimental_set_query_params(_=str(st.session_state.get("_rf", 0) + 1))

def _inject_global_css():
    """Dark theme + teal accent & card styling (called once)."""
    if st.session_state.get("_css_done"):
        return
    st.markdown(
        """
        <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600&display=swap"
              rel="stylesheet">
        <style>
        html, body, [class*="css"], .stApp{
            font-family:'Poppins',sans-serif;
            background:linear-gradient(135deg,#0E1117 0%,#1E222A 100%);
            color:#F6F7F9;
        }
        /* hide sidebar just on landing */
        [data-testid="stSidebar"], [data-testid="stSidebarResizer"]{
            display:none !important;
        }

        /* card buttons */
        button[kind="secondary"]{
            width:100%; height:100%;
            background:#1A1F29;
            border:2px solid #1ABC9C;
            border-radius:16px;
            padding:2.2rem 0.6rem !important;
            font-size:1.05rem; font-weight:600;
            color:#F6F7F9;
            transition:transform .15s ease, box-shadow .15s ease;
            white-space:normal; line-height:1.35;
        }
        button[kind="secondary"]:hover{
            transform:scale(1.04);
            box-shadow:0 0 12px rgba(26,188,156,0.6);
            background:#23303B;
            border-color:#1FDDC1;
            cursor:pointer;
        }

        /* back-to-menu button */
        .back-btn > button{
            background:#1ABC9C !important;
            border:none !important;
            font-weight:600;
            border-radius:10px !important;
        }
        .back-btn > button:hover{
            background:#1FDDC1 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.session_state["_css_done"] = True

# ───────────────────────────  LANDING GRID  ────────────────────────────────
def landing_menu(perms: dict, role: str):
    _inject_global_css()
    st.title("🗂️ **AMAS Portal**")
    st.caption("Select a module to begin")

    cols_per_row = 4
    rows = (len(PAGES) + cols_per_row - 1) // cols_per_row

    for r in range(rows):
        cols = st.columns(cols_per_row, gap="large")
        for c in range(cols_per_row):
            idx = r * cols_per_row + c
            if idx >= len(PAGES):
                continue

            label, icon, flag, _ = PAGES[idx]
            allowed = (
                True if flag is None else
                (role == "Admin" if flag == "ROLE_ADMIN" else perms.get(flag, False))
            )
            if not allowed:
                continue

            if cols[c].button(f"{icon}\n{label}", key=f"page_{label}", use_container_width=True):
                st.session_state["page"] = label
                _safe_rerun()

# ───────────────────────────  BACK BUTTON  ─────────────────────────────────
def back_to_menu():
    return st.container().button("⬅︎ Menu", key="back_to_menu", type="secondary")

# ───────────────────────────  MAIN FLOW  ───────────────────────────────────
def main() -> None:
    authenticate()
    perms = st.session_state.get("permissions", {})
    role  = st.session_state.get("user_role", "")

    current = st.session_state.get("page", "LANDING")

    if current == "LANDING":
        landing_menu(perms, role)
        return

    # back button on content pages
    with st.container().classed("back-btn"):
        if back_to_menu():
            st.session_state["page"] = "LANDING"
            _safe_rerun()
            return

    # routing
    for label, _icon, flag, func in PAGES:
        if current != label:
            continue
        allowed = (
            True if flag is None else
            (role == "Admin" if flag == "ROLE_ADMIN" else perms.get(flag, False))
        )
        if allowed:
            func()
        else:
            st.error("❌ You do not have permission to access this page.")
        break
    else:
        st.error("Unknown page.")

# ───────────────────────────  LAUNCH  ──────────────────────────────────────
if __name__ == "__main__":
    main()
