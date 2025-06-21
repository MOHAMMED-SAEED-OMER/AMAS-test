"""
Cashier ▸ Check-Out  (single-file, lazy auth import)
"""
from __future__ import annotations

import streamlit as st
from datetime import datetime, timezone
import pandas as pd
from db_handler import DatabaseManager        # ← this was always safe

_db    = DatabaseManager()
DENOMS = [50_000, 25_000, 10_000, 5_000, 1_000, 500, 250]

# ───────────────────────── helper SQL funcs ─────────────────────────
def get_shift_start(cashier: str):
    df = _db.fetch_data(
        "SELECT shift_end FROM cashier_shift_closure "
        "WHERE cashier=%s ORDER BY shift_end DESC LIMIT 1",
        (cashier,),
    )
    if not df.empty:
        return df.iat[0, 0]

    df = _db.fetch_data(
        "SELECT MIN(saletime) FROM sales "
        "WHERE cashier=%s AND saletime::date=CURRENT_DATE",
        (cashier,),
    )
    return df.iat[0, 0] if not df.empty else None


def get_sales_totals(cashier: str, start, end):
    df = _db.fetch_data(
        "SELECT SUM(finalamount) AS system_total, COUNT(*) AS tx_count "
        "FROM sales WHERE cashier=%s AND saletime BETWEEN %s AND %s",
        (cashier, start, end),
    )
    return float(df.iat[0, 0] or 0), int(df.iat[0, 1] or 0)


def get_item_summary(cashier: str, start, end) -> pd.DataFrame:
    return _db.fetch_data(
        """
        SELECT itemcode AS "Code",
               itemname AS "Item",
               SUM(quantity)                     AS "Qty",
               SUM(quantity * itemprice)         AS "IQD"
        FROM   sales_details
        WHERE  cashier=%s AND saletime BETWEEN %s AND %s
        GROUP  BY itemcode, itemname
        ORDER  BY "IQD" DESC
        """,
        (cashier, start, end),
    )


def save_closure(
    cashier, start, end,
    denom: dict[int, int],
    cash_total, system_total, notes: str
):
    _db.execute_command(
        """
        INSERT INTO cashier_shift_closure (
            cashier, shift_start, shift_end,
            system_total, cash_total,
            cnt_50000, cnt_25000, cnt_10000, cnt_5000,
            cnt_1000,  cnt_500,  cnt_250, notes
        ) VALUES (%(c)s,%(s)s,%(e)s,%(sys)s,%(cash)s,
                  %(n50)s,%(n25)s,%(n10)s,%(n5)s,
                  %(n1)s,%(n05)s,%(n025)s,%(notes)s);
        """,
        {
            "c": cashier, "s": start, "e": end,
            "sys": system_total, "cash": cash_total,
            "n50": denom[50_000], "n25": denom[25_000],
            "n10": denom[10_000], "n5": denom[5_000],
            "n1":  denom[1_000],  "n05": denom[500],
            "n025": denom[250],   "notes": notes,
        },
    )


def fetch_last_closure(cashier):
    df = _db.fetch_data(
        "SELECT * FROM cashier_shift_closure "
        "WHERE cashier=%s ORDER BY shift_end DESC LIMIT 1",
        (cashier,),
    )
    return df.iloc[0] if not df.empty else None

# ───────────────────────────── UI layer ───────────────────────────
def render():
    # 🔑 import auth helper *inside* the function
    from auth_utils import get_current_user

    st.markdown(
        "<h2 style='color:#1ABC9C;margin-bottom:0.2em'>🧾 Shift Check-Out</h2>",
        unsafe_allow_html=True,
    )

    user = get_current_user()
    if not user:
        st.error("Please sign in.")
        st.stop()

    cashier_email = user["email"]
    shift_start   = get_shift_start(cashier_email)
    if not shift_start:
        st.info("No sales recorded for today.")
        st.stop()

    now = datetime.now(tz=timezone.utc)
    system_total, tx_count = get_sales_totals(cashier_email, shift_start, now)

    # ── overview ──
    col1, col2, col3 = st.columns(3)
    col1.metric("Shift start", shift_start.strftime("%H:%M"))
    col2.metric("Total sales (IQD)", f"{system_total:,.0f}")
    col3.metric("# Transactions", tx_count)

    # ── item summary ──
    with st.expander("Sold-item breakdown"):
        st.dataframe(
            get_item_summary(cashier_email, shift_start, now),
            height=300, use_container_width=True,
        )

    # ── cash count ──
    st.subheader("Cash count")
    denom_counts, cash_total = {}, 0
    cols = st.columns(len(DENOMS))
    for i, d in enumerate(DENOMS):
        cnt = cols[i].number_input(f"{d:,}", 0, step=1, key=f"d_{d}")
        denom_counts[d] = cnt
        cash_total += cnt * d

    diff = cash_total - system_total
    st.markdown(
        f"<p style='font-size:1.1em'><strong>Your total:</strong> "
        f"{cash_total:,.0f} IQD ({'+' if diff>=0 else ''}{diff:,.0f})</p>",
        unsafe_allow_html=True,
    )

    notes = st.text_area("Notes / discrepancies")

    # ── submit ──
    if st.button("✅ Submit & Close Shift", type="primary"):
        save_closure(cashier_email, shift_start, now,
                     denom_counts, cash_total, system_total, notes)
        st.success("Shift closed and stored!")

        last = fetch_last_closure(cashier_email)
        if last is not None:
            st.divider()
            st.markdown("### 📄 Closure summary")
            c1, c2, c3 = st.columns(3)
            c1.metric("System total", f"{last.system_total:,.0f}")
            c2.metric("Counted cash", f"{last.cash_total:,.0f}")
            c3.metric("Δ", f"{last.discrepancy:+,.0f}",
                      delta_color="inverse")

            st.table(
                {
                    "Denomination": [f"{d:,}" for d in DENOMS],
                    "Count": [
                        last.cnt_50000, last.cnt_25000, last.cnt_10000,
                        last.cnt_5000,  last.cnt_1000,
                        last.cnt_500,   last.cnt_250,
                    ],
                }
            )
            if last.notes:
                st.info(f"**Notes:** {last.notes}")
        st.stop()

# dev entry-point
if __name__ == "__main__":
    render()
