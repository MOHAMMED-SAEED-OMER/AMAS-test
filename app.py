# app.py ── colourful card-grid navigation ───────────────────────────────────
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

# ─────────────────────────  NAV CONFIG  ────────────────────────────────────
PAGES = [
    ("Home",            "🏠", "CanAccessHome",        home.home),
    ("Item",            "📦", "CanAccessItems",       mainitem.item_page),
    ("Receive Items",   "📥", "CanAccessReceive",     main_receive_page),
    ("Purchase Order",  "🧾", "CanAccessPO",          mainpo.po_page),
    ("Selling Area",    "🛒", "CanAccessSellingArea", main_shelf_page),
    ("Cashier",         "💵", "CanAccessCashier",     main_cashier_page),
    ("Finance",         "💰", "CanAccessFinance",     main_finance_page),
    ("Returns",         "↩️", "CanAccessReturns",     main_return_page),
    ("Issues",          "🐞", "CanAccessIssues",      issues_page),
    ("Shelf Map",       "🗺️", "CanAccessShelfMap",   shelf_map_page),
    ("Reports",         "📊", "CanAccessReports",     main_reports.reports_page),
    ("User Management", "🛠️", "ROLE_ADMIN",          show_user_admin),
    ("Assets",          "💼", None, lambda: st.info("Assets page WIP")),
    ("Supplier",        "🚚", None, lambda: st.info("Supplier page WIP")),
]

# ─────────────────────────  UTILS  ─────────────────────────────────────────
def _safe_rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    elif hasattr(st, "experimental_rerun"):
        st.experimental_rerun()

def _inject_base_css():
    if st.session_state.get("_css_done"):
        return
    st.markdown(
        """
        <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600&display=swap"
              rel="stylesheet">
        <style>
        html,body,[class*="css"],.stApp{
            font-family:'Poppins',sans-serif;
            background:linear-gradient(120deg,#f6d365 0%, #fda085 100%);
            background-attachment:fixed;
            color:#fafbfc;
        }
        /* colourful card buttons */
        button[kind="secondary"]{
            width:100%; height:100%;
            padding:2.3rem 0.7rem !important;
            font-size:1.05rem; font-weight:600; line-height:1.35;
            border:none; border-radius:18px;
            color:#ffffff; cursor:pointer;
            transition:transform .15s ease, box-shadow .2s ease;
        }
        button[kind="secondary"]:nth-child(7n+1){background:linear-gradient(135deg,#ff9a9e 0%,#fecfef 100%);}
        button[kind="secondary"]:nth-child(7n+2){background:linear-gradient(135deg,#a18cd1 0%,#fbc2eb 100%);}
        button[kind="secondary"]:nth-child(7n+3){background:linear-gradient(135deg,#fddb92 0%,#d1fdff 100%);}
        button[kind="secondary"]:nth-child(7n+4){background:linear-gradient(135deg,#84fab0 0%,#8fd3f4 100%);}
        button[kind="secondary"]:nth-child(7n+5){background:linear-gradient(135deg,#cfd9df 0%,#e2ebf0 100%);}
        button[kind="secondary"]:nth-child(7n+6){background:linear-gradient(135deg,#f6d365 0%,#fda085 100%);}
        button[kind="secondary"]:nth-child(7n+7){background:linear-gradient(135deg,#a6c0fe 0%,#f68084 100%);}
        button[kind="secondary"]:hover{
            transform:translateY(-4px) scale(1.03);
            box-shadow:0 6px 14px rgba(0,0,0,.25);
        }
        /* frosted-glass back button */
        button[id="back_to_menu"]{
            backdrop-filter:blur(10px);
            background:rgba(255,255,255,0.18) !important;
            border:1px solid rgba(255,255,255,0.4) !important;
            padding:0.5rem 1.3rem !important;
            border-radius:12px !important;
            font-weight:600; color:#fff !important;
            margin-bottom:1rem;
        }
        button[id="back_to_menu"]:hover{
            background:rgba(255,255,255,0.32) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.session_state["_css_done"] = True

def _hide_sidebar_css():
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"],[data-testid="stSidebarResizer"]{
            display:none !important;
        }
        .stApp{padding-left:1rem;padding-right:1rem;}
        </style>
        """,
        unsafe_allow_html=True,
    )

# ─────────────────────────  LANDING GRID  ─────────────────────────────────
def landing_menu(perms: dict, role: str):
    _hide_sidebar_css()
    st.title("✨ **AMAS Portal**")
    st.caption("Choose a module to get started")

    cols_per_row = 4
    rows = (len(PAGES)+cols_per_row-1)//cols_per_row

    for r in range(rows):
        cols = st.columns(cols_per_row, gap="large")
        for c in range(cols_per_row):
            idx = r*cols_per_row + c
            if idx >= len(PAGES): continue
            label, icon, flag, _ = PAGES[idx]
            allowed = (flag is None) or (
                role=="Admin" if flag=="ROLE_ADMIN" else perms.get(flag, False)
            )
            if not allowed: continue

            if cols[c].button(f"{icon}\n{label}", key=f"page_{label}", use_container_width=True):
                st.session_state["page"] = label
                _safe_rerun()

# ─────────────────────────  BACK BUTTON  ─────────────────────────────────
def back_to_menu():
    return st.button("⬅︎ Menu", key="back_to_menu")

# ─────────────────────────  MAIN FLOW  ───────────────────────────────────
def main() -> None:
    _inject_base_css()
    auth_ok = authenticate()          # ← whatever your function returns

    # ①  FORCE landing page right after a successful login
    if auth_ok:
        st.session_state["page"] = "LANDING"

    perms = st.session_state.get("permissions", {})
    role  = st.session_state.get("user_role", "")
    current = st.session_state.get("page", "LANDING")

    # ② landing grid
    if current == "LANDING":
        landing_menu(perms, role)
        return

    # ③ back button on content pages
    if back_to_menu():
        st.session_state["page"] = "LANDING"
        _safe_rerun()
        return

    # ④ routing
    for label, _icon, flag, func in PAGES:
        if current != label:
            continue
        allowed = (flag is None) or (
            role=="Admin" if flag=="ROLE_ADMIN" else perms.get(flag, False)
        )
        if allowed:
            func()
        else:
            st.error("❌ You do not have permission to access this page.")
        break
    else:
        st.error("Unknown page.")

# ─────────────────────────  RUN  ──────────────────────────────────────────
if __name__ == "__main__":
    main()
