"""
Cashier ▸ Check-Out  (single-file edition)

• Shows shift totals and item breakdown for the current cashier.
• Lets the cashier enter bill counts, see any cash / system delta,
  and stores everything in `cashier_shift_closure`.
"""
from __future__ import annotations

import streamlit as st
from datetime import datetime, timezone
import pandas as pd

# absolute import – same style you use for db_handler
from auth_utils import get_current_user
from db_handler import DatabaseManager

# ─────────────────────────── constants / setup ──────────────────────────────
_db = DatabaseManager()                         # one cached connection per session
DENOMS = [50_000, 25_000, 10_000, 5_000, 1_000, 500, 250]  # IQD bills

# ───────────────────────────── helper functions ─────────────────────────────
def get_shift_start(cashier: str):
    """Start of the *current* open shift for this cashier."""
    # after last closure, if any
    df = _db.fetch_data(
        "SELECT shift_end FROM cashier_shift_closure "
        "WHERE cashier = %s ORDER BY shift_end DESC LIMIT 1",
        (cashier,),
    )
    if not df.empty:
        return df.iat[0, 0]

    # else first sale today
    df = _db.fetch_data(
        "SELECT MIN(saletime) FROM sales "
        "WHERE cashier = %s AND saletime::date = CURRENT_DATE",
        (cashier,),
    )
    return df.iat[0, 0] if not df.empty else None


def get_sales_totals(cashier: str, start: datetime, end: datetime):
    df = _db.fetch_data(
        "SELECT SUM(finalamount) AS system_total, "
        "       COUNT(*)         AS tx_count "
        "FROM   sales "
        "WHERE  cashier = %s AND saletime BETWEEN %s AND %s",
        (cashier, start, end),
    )
    return float(df.iat[0, 0] or 0), int(df.iat[0, 1] or 0)


def get_item_summary(cashier: str, start: datetime, end: datetime) -> pd.DataFrame:
    return _db.fetch_data(
        """
        SELECT itemcode AS "Code",
               itemname AS "Item",
               SUM(quantity)                     AS "Qty",
               SUM(quantity * itemprice)         AS "IQD"
        FROM   sales_details                     -- line-item table
        WHERE  cashier = %s AND saletime BETWEEN %s AND %s
        GROUP  BY itemcode, itemname
        ORDER  BY "IQD" DESC
        """,
        (cashier, start, end),
    )


def save_closure(
    cashier: str,
    start: datetime,
    end: datetime,
    denom: dict[int, int],
    cash_total: float,
    system_total: float,
    notes: str,
):
    sql = """
    INSERT INTO cashier_shift_closure (
        cashier, shift_start, shift_end,
        system_total, cash_total,
        cnt_50000, cnt_25000, cnt_10000, cnt_5000,
        cnt_1000,  cnt_500,  cnt_250,
        notes
    ) VALUES (%(c)s, %(s)s, %(e)s,
              %(sys)s, %(cash)s,
              %(n50)s, %(n25)s, %(n10)s, %(n5)s,
              %(n1)s,  %(n05)s, %(n025)s,
              %(notes)s);
    """
    _db.execute_command(
        sql,
        {
            "c": cashier,
            "s": start,
            "e": end,
            "sys": system_total,
            "cash": cash_total,
            "n50": denom.get(50_000, 0),
            "n25": denom.get(25_000, 0),
            "n10": denom.get(10_000, 0),
            "n5":  denom.get(5_000, 0),
            "n1":  denom.get(1_000, 0),
            "n05": denom.get(500, 0),
            "n025": denom.get(250, 0),
            "notes": notes,
        },
    )


def fetch_last_closure(cashier: str):
    df = _db.fetch_data(
        "SELECT * FROM cashier_shift_closure "
        "WHERE cashier = %s ORDER BY shift_end DESC LIMIT 1",
        (cashier,),
    )
    return df.iloc[0] if not df.empty else None

# ──────────────────────────────── UI layer ──────────────────────────────────
def render():
    st.markdown(
        "<h2 style='color:#1ABC9C;margin-bottom:0.2em'>🧾 Shift Check-Out</h2>",
        unsafe_allow_html=True,
    )

    user = get_current_user()
    if not user:
        st.error("Please sign in.")
        st.stop()

    email = user["email"]
    shift_start = get_shift_start(email)
    if not shift_start:
        st.info("No sales recorded for today.")
        st.stop()

    now = datetime.now(tz=timezone.utc)
    system_total, tx_count = get_sales_totals(email, shift_start, now)

    # A - overview
    c1, c2, c3 = st.columns(3)
    c1.metric("Shift start", shift_start.strftime("%H:%M"))
    c2.metric("Total sales (IQD)", f"{system_total:,.0f}")
    c3.metric("# Transactions", tx_count)

    # B - item summary
    with st.expander("Sold-item breakdown"):
        st.dataframe(
            get_item_summary(email, shift_start, now),
            height=300,
            use_container_width=True,
        )

    # C - cash count
    st.subheader("Cash count")
    denom_counts, cash_total = {}, 0
    cols = st.columns(len(DENOMS))
    for idx, d in enumerate(DENOMS):
        cnt = cols[idx].number_input(f"{d:,}", min_value=0, step=1, key=f"d_{d}")
        denom_counts[d] = cnt
        cash_total += cnt * d

    diff = cash_total - system_total
    st.markdown(
        f"<p style='font-size:1.1em'>"
        f"<strong>Your total:</strong> {cash_total:,.0f} IQD "
        f"({'+' if diff >= 0 else ''}{diff:,.0f})</p>",
        unsafe_allow_html=True,
    )

    notes = st.text_area("Notes / discrepancies")

    # D - submit
    if st.button("✅ Submit & Close Shift", type="primary"):
        save_closure(email, shift_start, now,
                     denom_counts, cash_total, system_total, notes)
        st.success("Shift closed and stored!")

        last = fetch_last_closure(email)
        if last is not None:
            st.divider()
            st.markdown(
