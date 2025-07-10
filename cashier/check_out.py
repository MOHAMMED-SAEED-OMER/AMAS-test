"""
Cashier ▸ Check-Out  (MySQL backend)
"""
from __future__ import annotations

from datetime import datetime
import pandas as pd
import streamlit as st

from db_handler import DatabaseManager

_db = DatabaseManager()
DENOMS = [50_000, 25_000, 10_000, 5_000, 1_000, 500, 250]

# ───────────────────────── helpers ──────────────────────────
def _to_plain_datetime(ts):
    """Return a naïve (no tzinfo) datetime or None."""
    if ts is None:
        return None
    if isinstance(ts, pd.Timestamp):
        ts = ts.to_pydatetime()
    # leave tz-aware values as local naive
    return ts.replace(tzinfo=None) if ts.tzinfo else ts

def _fmt_money(val) -> str:
    return "N/A" if val is None else f"{float(val):,.0f}"

# ---------- helper SQL functions ----------
def get_shift_start(cashier: str):
    # last recorded closure
    df = _db.fetch_data(
        """
        SELECT shift_end
        FROM   cashier_shift_closure
        WHERE  cashier = %s
        ORDER  BY shift_end DESC
        LIMIT 1
        """,
        (cashier,),
    )
    if not df.empty and df.iat[0, 0]:
        return _to_plain_datetime(df.iat[0, 0])

    # otherwise: first sale today
    df = _db.fetch_data(
        """
        SELECT MIN(saletime)
        FROM   sales
        WHERE  cashier = %s
          AND  DATE(saletime) = CURDATE()
        """,
        (cashier,),
    )
    return _to_plain_datetime(df.iat[0, 0]) if not df.empty else None

def get_sales_totals(cashier: str, start, end):
    start = _to_plain_datetime(start)
    end   = _to_plain_datetime(end)
    df = _db.fetch_data(
        """
        SELECT SUM(finalamount) AS system_total,
               COUNT(*)         AS tx_count
        FROM   sales
        WHERE  cashier = %s
          AND  saletime BETWEEN %s AND %s
        """,
        (cashier, start, end),
    )
    return float(df.iat[0, 0] or 0), int(df.iat[0, 1] or 0)

def get_item_summary(cashier: str, start, end) -> pd.DataFrame:
    start = _to_plain_datetime(start)
    end   = _to_plain_datetime(end)
    return _db.fetch_data(
        """
        SELECT  i.itemid                 AS "ID",
                i.itemnameenglish        AS "Item",
                SUM(si.quantity)         AS "Qty",
                SUM(si.quantity * si.unitprice) AS "IQD"
        FROM    salesitems si
        JOIN    sales      s  ON s.saleid = si.saleid
        JOIN    item       i  ON i.itemid = si.itemid
        WHERE   s.cashier = %s
          AND   s.saletime BETWEEN %s AND %s
        GROUP BY i.itemid, i.itemnameenglish
        ORDER BY `IQD` DESC
        """,
        (cashier, start, end),
    )

def save_closure(
    cashier,
    start,
    end,
    denom,
    cash_total,
    system_total,
    notes,
):
    disc = cash_total - system_total
    payload = {
        "c":    cashier,
        "s":    _to_plain_datetime(start),
        "e":    _to_plain_datetime(end),
        "sys":  system_total,
        "cash": cash_total,
        "disc": disc,
        "n50":  denom.get(50_000, 0),
        "n25":  denom.get(25_000, 0),
        "n10":  denom.get(10_000, 0),
        "n5":   denom.get(5_000, 0),
        "n1":   denom.get(1_000, 0),
        "n05":  denom.get(500,    0),
        "n025": denom.get(250,    0),
        "notes": notes,
    }
    _db.execute_command(
        """
        INSERT INTO cashier_shift_closure (
            cashier, shift_start, shift_end,
            system_total, cash_total, discrepancy,
            cnt_50000, cnt_25000, cnt_10000, cnt_5000,
            cnt_1000,  cnt_500,  cnt_250, notes
        ) VALUES (%(c)s, %(s)s, %(e)s,
                  %(sys)s, %(cash)s, %(disc)s,
                  %(n50)s, %(n25)s, %(n10)s, %(n5)s,
                  %(n1)s, %(n05)s, %(n025)s, %(notes)s)
        """,
        payload,
    )

def fetch_last_closure(cashier):
    df = _db.fetch_data(
        """
        SELECT *
        FROM   cashier_shift_closure
        WHERE  cashier = %s
        ORDER  BY shift_end DESC
        LIMIT 1
        """,
        (cashier,),
    )
    return df.iloc[0] if not df.empty else None

# ---------- UI ----------
def render():
    st.markdown(
        "<h2 style='color:#1ABC9C;margin-bottom:0.2em'>🧾 Shift Check-Out</h2>",
        unsafe_allow_html=True,
    )

    cashier_email = st.session_state.get("user_email")
    if not cashier_email:
        st.error("Please sign in.")
        st.stop()

    shift_start = get_shift_start(cashier_email)
    if not shift_start:
        st.info("No sales recorded for today.")
        st.stop()

    now = datetime.now()              # ← local time, not UTC
    system_total, tx_count = get_sales_totals(cashier_email, shift_start, now)

    # Overview
    c1, c2, c3 = st.columns(3)
    c1.metric("Shift start", shift_start.strftime("%H:%M"))
    c2.metric("Total sales (IQD)", _fmt_money(system_total))
    c3.metric("# Transactions", tx_count)

    # Item breakdown
    with st.expander("Sold-item breakdown"):
        st.dataframe(
            get_item_summary(cashier_email, shift_start, now),
            height=300,
            use_container_width=True,
        )

    # Cash count
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
        f"{_fmt_money(cash_total)} IQD "
        f"({'+' if diff>=0 else ''}{_fmt_money(diff)})</p>",
        unsafe_allow_html=True,
    )

    notes = st.text_area("Notes / discrepancies")

    if st.button("✅ Submit & Close Shift", type="primary"):
        save_closure(
            cashier_email,
            shift_start,
            now,
            denom_counts,
            cash_total,
            system_total,
            notes,
        )
        st.success("Shift closed and stored!")

        last = fetch_last_closure(cashier_email)
        if last is not None:
            st.divider()
            st.markdown("### 📄 Closure summary")
            a, b, c = st.columns(3)
            a.metric("System total", _fmt_money(last.system_total))
            b.metric("Counted cash", _fmt_money(last.cash_total))
            c.metric("Δ", _fmt_money(last.discrepancy), delta_color="inverse")

            st.table(
                {
                    "Denomination": [f"{d:,}" for d in DENOMS],
                    "Count": [
                        last.cnt_50000 or 0,
                        last.cnt_25000 or 0,
                        last.cnt_10000 or 0,
                        last.cnt_5000  or 0,
                        last.cnt_1000  or 0,
                        last.cnt_500   or 0,
                        last.cnt_250   or 0,
                    ],
                }
            )
            if last.notes:
                st.info(f"**Notes:** {last.notes}")
        st.stop()

if __name__ == "__main__":
    render()
