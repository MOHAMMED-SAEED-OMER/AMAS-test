# app.py ──────────────────────────────────────────────────────────────────────
import streamlit as st
st.set_page_config(page_title="Inventory Management System", layout="wide")

# ── Page modules (unchanged) ────────────────────────────────────────────────
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

# ─────────────────────────  CARD MENU CONFIG  ───────────────────────────────
# label, icon, permission flag (or special check), callback function
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
    # add empty slots or future pages so you reach 14 visible cards
    ("Assets",         "💼", None,                  lambda: st.info("Assets page WIP")),
    ("Supplier",       "🚚", None,                  lambda: st.info("Supplier page WIP")),
]

# ─────────────────────────  HELPER: HIDE SIDEBAR  ───────────────────────────
def _hide_sidebar():
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"], [data-testid="stSidebarResizer"]{
            display:none !important;
        }
        .stApp {padding-left:1rem; padding-right:1rem;}
        /* card-style buttons */
        button[kind="secondary"]{
            width:100%; height:100%;
            padding:2rem 0.5rem !important;
            font-size:1.05rem; font-weight:600;
            border:2px solid #5c8df6; border-radius:12px;
            background:#eef2ff;
            white-space:normal;
        }
        button[kind="secondary"]:hover{background:#dbe4ff;}
        </style>
        """,
        unsafe_allow_html=True,
    )

# ─────────────────────────  LANDING GRID  ───────────────────────────────────
def landing_menu(perms: dict, role: str):
    _hide_sidebar()
    st.title("🗂️ AMAS Portal")

    cols_per_row = 4      # 4×4 grid = 16 slots → room for 14 cards
    rows = (len(PAGES) + cols_per_row - 1) // cols_per_row

    for r in range(rows):
        cols = st.columns(cols_per_row, gap="large")
        for c in range(cols_per_row):
            idx = r * cols_per_row + c
            if idx >= len(PAGES):
                continue

            label, icon, flag, _ = PAGES[idx]

            # permission check: flag == None  → always show
            allowed = (
                True if flag is None else
                (role == "Admin" if flag == "ROLE_ADMIN" else perms.get(flag, False))
            )
            if not allowed:
                continue  # hide card

            if cols[c].button(f"{icon}\n{label}", key=f"page_{label}", use_container_width=True):
                st.session_state["page"] = label
                st.experimental_rerun()

# ─────────────────────────  MAIN  ───────────────────────────────────────────
def main() -> None:
    authenticate()                                # ← your login flow
    perms = st.session_state.get("permissions", {})
    role  = st.session_state.get("user_role", "")

    current = st.session_state.get("page", "LANDING")

    # landing screen
    if current == "LANDING":
        landing_menu(perms, role)
        return

    # route to selected page
    for label, _icon, flag, func in PAGES:
        if current != label:
            continue

        # final permission check
        if flag is None or (flag == "ROLE_ADMIN" and role == "Admin") or perms.get(flag, False):
            func()
        else:
            st.error("❌ You do not have permission to access this page.")
        break
    else:
        st.error("Unknown page.")

# ─────────────────────────  RUN  ────────────────────────────────────────────
if __name__ == "__main__":
    main()
