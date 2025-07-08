"""
Cashier ▸ Check-Out  (MySQL backend)
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from db_handler import DatabaseManager

_db = DatabaseManager()
DENOMS = [50_000, 25_000, 10_000, 5_000, 1_000, 500, 250]


# ───────────────────────── helpers ──────────────────────────
def _to_plain_datetime(ts) -> datetime:
    """Convert pandas Timestamp or tz-aware datetime → naïve datetime."""
    if isinstance(ts, pd.Timestamp):
        ts = ts.to_pydatetime()
    if ts.tzinfo is not None:
        ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
    return ts


# ---------- helper SQL functions ----------
def get_shift_start(cashier: str):
    # last recorded closure
    df = _db.fetch_data(
        """
        SELECT shift_end
        FROM   `cashier_shift_closure`
        WHERE  cashier = %s
        ORDER  BY shift_end DESC
        LIMIT 1
        """,
        (cashier,),
    )
    if not df.empty:
        return _to_plain_datetime(df.iat[0, 0])

    # otherwise: first sale *today*
    df = _db.fetch_data(
        """
        SELECT MIN(saletime)
        FROM   `sales`
        WHERE  cashier = %s
          AND  DATE(saletime) = CURDATE()
        """,
        (cashier,),
    )
    return _to_plain_datetime(df.iat[0, 0]) if not df.empty else None


def get_sales_totals(cashier: str, start, end):
    start = _to_plain_datetime(start)
    end = _to_plain_datetime(end)

    df = _db.fetch_data(
        """
        SELECT SUM(finalamount) AS system_total,
               COUNT(*)         AS tx_count
        FROM   `sales`
        WHERE  cashier = %s
          AND  saletime BETWEEN %s AND %s
        """,
        (cashier, start, end),
    )
    return float(df.iat[0, 0] or 0), int(df.iat[0, 1] or 0)


def get_item_summary(cashier: str, start, end) -> pd.DataFrame:
    start = _to_plain_datetime(start)
    end = _to_plain_datetime(end)

    return _db.fetch_data(
        """
        SELECT  i.itemid                 AS "ID",
                i.itemnameenglish        AS "Item",
                SUM(si.quantity)         AS "Qty",
                SUM(si.quantity * si.unitprice) AS "IQD"
        FROM    `salesitems` si
        JOIN    `sales`      s  ON s.saleid = si.saleid
        JOIN    `item`       i  ON i.itemid = si.itemid
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
    start = _to_plain_datetime(start)
    end = _to_plain_datetime(end)

    _db.execute_command(
        """
        INSERT INTO `cashier_shift_closure` (
            cashier, shift_start, shift_end,
            system_total, cash_total,
            cnt_50000, cnt_25000, cnt_10000, cnt_5000,
            cnt_1000,  cnt_500,  cnt_250, notes
        ) VALUES (%(c)s, %(s)s, %(e)s, %(sys)s, %(cash)s,
                  %(n50)s, %(n25)s, %(n10)s, %(n5)s,
                  %(n1)s, %(n05)s, %(n025)s, %(notes)s)
        """,
        {
            "c": cashier,
            "s": start,
            "e": end,
            "sys": system_total,
            "cash": cash_total,
            "n50": denom[50_000],
            "n25": denom[25_000],
            "n10": denom[10_000],
            "n5": denom[5_000],
            "n1": denom[1_000],
            "n05": denom[500],
            "n025": denom[250],
            "notes": notes,
        },
    )


def fetch_last_closure(cashier):
    df = _db.fetch_data(
        """
        SELECT *
        FROM   `cashier_shift_closure`
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

    now = _to_plain_datetime(datetime.utcnow())
    system_total, tx_count = get_sales_totals(cashier_email, shift_start, now)

    # Overview
    c1, c2, c3 = st.columns(3)
    c1.metric("Shift start", shift_start.strftime("%H:%M"))
    c2.metric("Total sales (IQD)", f"{system_total:,.0f}")
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
        (
            "<p style='font-size:1.1em'><strong>Your total:</strong> "
            f"{cash_total:,.0f} IQD "
            f"({'+' if diff>=0 else ''}{diff:,.0f})</p>"
        ),
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
            a.metric("System total", f"{last.system_total:,.0f}")
            b.metric("Counted cash", f"{last.cash_total:,.0f}")
            c.metric("Δ", f"{last.discrepancy:+,.0f}", delta_color="inverse")

            st.table(
                {
                    "Denomination": [f"{d:,}" for d in DENOMS],
                    "Count": [
                        last.cnt_50000,
                        last.cnt_25000,
                        last.cnt_10000,
                        last.cnt_5000,
                        last.cnt_1000,
                        last.cnt_500,
                        last.cnt_250,
                    ],
                }
            )
            if last.notes:
                st.info(f"**Notes:** {last.notes}")
        st.stop()


if __name__ == "__main__":
    render()
