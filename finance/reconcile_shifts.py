"""
Finance ▸ Reconcile Shifts
Shows each cashier-shift closure that hasn’t been reviewed yet.
Finance can approve or adjust the amount and leave a note.
"""

from __future__ import annotations
import streamlit as st
from datetime import datetime, timezone
from db_handler import DatabaseManager

_db = DatabaseManager()                         # shared Neon helper


# ───────────────────────── DB helpers ──────────────────────────
def fetch_pending():
    """All closures that Finance hasn’t reviewed yet."""
    return _db.fetch_data(
        """
        SELECT *
        FROM   cashier_shift_closure
        WHERE  finance_checked = FALSE
        ORDER  BY shift_end DESC
        """
    )


def fetch_recent_approved(days: int = 7):
    """Last few days of already-approved closures (for quick reference)."""
    return _db.fetch_data(
        """
        SELECT *
        FROM   cashier_shift_closure
        WHERE  finance_checked = TRUE
          AND  finance_checked_at >= CURRENT_DATE - %s::INT
        ORDER  BY finance_checked_at DESC
        """,
        (days,),
    )


def approve_shift(row, approved_amt: float, note: str, finance_email: str):
    """Mark closure as checked (with optional adjustment)."""
    _db.execute_command(
        """
        UPDATE cashier_shift_closure
           SET finance_checked      = TRUE,
               finance_checked_at   = NOW(),
               finance_checked_by   = %s,
               finance_approved_amount = %s,
               finance_note         = %s
         WHERE closure_id = %s
        """,
        (
            finance_email,
            approved_amt,
            note,
            int(row["closure_id"]),
        ),
    )


# ─────────────────────────── UI ───────────────────────────────
def reconcile_shifts_tab():
    st.subheader("💳 Reconcile Cashier Shifts")

    finance_email = st.session_state.get("user_email", "finance@local")
    pending_df    = fetch_pending()

    if pending_df.empty:
        st.success("No pending shifts — all caught up!")
    else:
        st.info(f"**{len(pending_df)} shift(s)** need reconciliation.")
        for _, row in pending_df.iterrows():
            with st.expander(
                f"{row.cashier} — Shift ended {row.shift_end:%d %b %H:%M}"
            ):
                col1, col2, col3 = st.columns(3)
                col1.metric("System total",  f"{row.system_total:,.0f}")
                col2.metric("Counted cash",  f"{row.cash_total:,.0f}")
                col3.metric("Δ",             f"{row.discrepancy:+,.0f}",
                            delta_color="inverse")

                # Bill breakdown
                bill_cols = {
                    50_000: row.cnt_50000, 25_000: row.cnt_25000,
                    10_000: row.cnt_10000,  5_000: row.cnt_5000,
                     1_000: row.cnt_1000,     500: row.cnt_500,
                       250: row.cnt_250,
                }
                st.table({
                    "Denomination": [f"{d:,}" for d in bill_cols],
                    "Count": list(bill_cols.values()),
                })

                st.markdown("---")
                adj_amt = st.number_input(
                    "Approved amount (IQD)",
                    value=float(row.cash_total),
                    step=1000.0,
                    key=f"approve_amt_{row.closure_id}",
                )
                note = st.text_area(
                    "Finance note (optional)",
                    key=f"note_{row.closure_id}",
                )
                if st.button("✅ Approve", key=f"approve_btn_{row.closure_id}"):
                    approve_shift(row, adj_amt, note, finance_email)
                    st.success("Shift reconciled.")
                    st.experimental_rerun()

    # Recently approved
    appr_df = fetch_recent_approved()
    with st.expander("✅ Recently approved (last 7 days)"):
        if appr_df.empty:
            st.write("Nothing yet.")
        else:
            disp = appr_df[[
                "cashier", "shift_end", "cash_total",
                "finance_approved_amount", "finance_checked_by",
                "finance_checked_at",
            ]].rename(columns={
                "cashier": "Cashier",
                "shift_end": "Ended",
                "cash_total": "Counted",
                "finance_approved_amount": "Approved",
                "finance_checked_by": "By",
                "finance_checked_at": "When",
            })
            st.dataframe(disp, use_container_width=True, hide_index=True)


# for standalone debug
if __name__ == "__main__":
    st.set_page_config(page_title="Reconcile Shifts", layout="wide")
    reconcile_shifts_tab()
