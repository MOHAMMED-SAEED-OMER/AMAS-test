"""
Cashier ▸ Check-Out  (MySQL backend, UTC-based like the old PostgreSQL version)
"""
from __future__ import annotations

from datetime import datetime, timezone
import pandas as pd
import streamlit as st

from db_handler import DatabaseManager

_db    = DatabaseManager()
DENOMS = [50_000, 25_000, 10_000, 5_000, 1_000, 500, 250]

# ───────────────────────── helpers ──────────────────────────
def _to_plain_datetime(ts):
    """Make any Timestamp/aware-dt into a naïve UTC datetime (clock unchanged)."""
    if ts is None:
        return None
    if isinstance(ts, pd.Timestamp):
        ts = ts.to_pydatetime()
    return ts.replace(tzinfo=None)

def _fmt(val):
    return "N/A" if val is None else f"{float(val):,.0f}"

# ───────────────────────── SQL helpers ──────────────────────
def get_shift_start(cashier: str):
    # 1️⃣ last recorded closure for this cashier
    df = _db.fetch_data(
        """
        SELECT shift_end
        FROM   cashier_shift_closure
        WHERE  cashier = %s
        ORDER  BY shift_end DESC
        LIMIT  1
        """,
        (cashier,),
    )
    if not df.empty and df.iat[0, 0]:
        return _to_plain_datetime(df.iat[0, 0])

    # 2️⃣ else earliest sale *today* (server uses UTC)
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
    df = _db.fetch_data(
        """
        SELECT SUM(finalamount) AS system_total,
               COUNT(*)         AS tx_count
        FROM   sales
        WHERE  cashier = %s
          AND  saletime BETWEEN %s AND %s
        """,
        (cashier, _to_plain_datetime(start), _to_plain_datetime(end)),
    )
    return float(df.iat[0, 0] or 0), int(df.iat[0, 1] or 0)

def get_item_summary(cashier: str, start, end):
    return _db.fetch_data(
        """
        SELECT  i.itemid          AS "ID",
                i.itemnameenglish AS "Item",
                SUM(si.quantity)  AS "Qty",
                SUM(si.quantity * si.unitprice) AS "IQD"
        FROM    salesitems si
        JOIN    sales      s  ON s.saleid = si.saleid
        JOIN    item       i  ON i.itemid = si.itemid
        WHERE   s.cashier = %s
          AND   s.saletime BETWEEN %s AND %s
        GROUP BY i.itemid, i.itemnameenglish
        ORDER BY "IQD" DESC
        """,
        (cashier, _to_plain_datetime(start), _to_plain_datetime(end)),
    )

def save_closure(cashier, start, end, denom, cash_total, system_total, notes):
    disc = cash_total - system_total
    _db.execute_command(
        """
        INSERT INTO cashier_shift_closure (
            cashier, shift_start, shift_end,
            system_total, cash_total, discrepancy,
            cnt_50000, cnt_25000, cnt_10000, cnt_5000,
            cnt_1000,  cnt_500,  cnt_250, notes
        ) VALUES (%(c)s,%(s)s,%(e)s,%(sys)s,%(cash)s,%(disc)s,
                  %(n50)s,%(n25)s,%(n10)s,%(n5)s,
                  %(n1)s,%(n05)s,%(n025)s,%(notes)s)
        """,
        {
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
        },
    )

def fetch_last_closure(cashier):
    df = _db.fetch_data(
        """
        SELECT *
        FROM   cashier_shift_closure
        WHERE  cashier = %s
        ORDER  BY shift_end DESC
        LIMIT  1
        """,
        (cashier,),
    )
    return df.iloc[0] if not df.empty else None

# ───────────────────────── UI  ──────────────────────────────
def render():
    st.markdown(
        "<h2 style='color:#1ABC9C;margin-bottom:0.3em'>🧾 Shift Check-Out</h2>",
        unsafe_allow_html=True,
    )

    cashier = st.session_state.get("user_email")
    if not cashier:
        st.error("Please sign in.")
        st.stop()

    shift_start = get_shift_start(cashier)
    if not shift_start:
        st.info("No sales recorded for today.")
        st.stop()

    now = datetime.utcnow()
    # ─── DEBUG ───
with st.expander("DEBUG – shift window"):
    st.write("cashier =", cashier)
    st.write("shift_start =", shift_start, type(shift_start))
    st.write("now =", now)

    system_total, tx_count = get_sales_totals(cashier, shift_start, now)

    # Overview
    c1, c2, c3 = st.columns(3)
    c1.metric("Shift start", shift_start.strftime("%H:%M"))
    c2.metric("Total sales (IQD)", _fmt(system_total))
    c3.metric("# Transactions", tx_count)

    # Item breakdown
    with st.expander("Sold-item breakdown"):
        st.dataframe(
            get_item_summary(cashier, shift_start, now),
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
        f"{_fmt(cash_total)} IQD "
        f"({'+' if diff>=0 else ''}{_fmt(diff)})</p>",
        unsafe_allow_html=True,
    )

    notes = st.text_area("Notes / discrepancies")

    if st.button("✅ Submit & Close Shift", type="primary"):
        save_closure(cashier, shift_start, now,
                     denom_counts, cash_total, system_total, notes)
        st.success("Shift closed and stored!")

        last = fetch_last_closure(cashier)
        if last is not None:
            st.divider()
            st.markdown("### 📄 Closure summary")
            a, b, c = st.columns(3)
            a.metric("System total", _fmt(last.system_total))
            b.metric("Counted cash", _fmt(last.cash_total))
            c.metric("Δ", _fmt(last.discrepancy), delta_color="inverse")

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
