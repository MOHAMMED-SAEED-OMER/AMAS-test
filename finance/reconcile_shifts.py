"""
Finance ▸ Reconcile Shifts
Finance staff can review each cashier shift, adjust bill counts
if needed, approve, and leave a note.
"""

from __future__ import annotations
import streamlit as st
from db_handler import DatabaseManager

_db = DatabaseManager()
DENOMS = [50_000, 25_000, 10_000, 5_000, 1_000, 500, 250]

# ───────────────────────── DB helpers ──────────────────────────
def fetch_pending():
    return _db.fetch_data(
        """SELECT * FROM cashier_shift_closure
           WHERE finance_checked = FALSE
           ORDER BY shift_end DESC"""
    )


def fetch_recent(days: int = 7):
    return _db.fetch_data(
        """SELECT * FROM cashier_shift_closure
           WHERE finance_checked = TRUE
             AND finance_checked_at >= CURRENT_DATE - %s::INT
           ORDER BY finance_checked_at DESC""",
        (days,),
    )


def update_with_finance(
    closure_id: int,
    counts: dict[int, int],
    approved_amt: float,
    note: str,
    finance_email: str,
):
    _db.execute_command(
        """
        UPDATE cashier_shift_closure
           SET finance_cnt_50000 = %(n50)s,
               finance_cnt_25000 = %(n25)s,
               finance_cnt_10000 = %(n10)s,
               finance_cnt_5000  = %(n5)s,
               finance_cnt_1000  = %(n1)s,
               finance_cnt_500   = %(n05)s,
               finance_cnt_250   = %(n025)s,
               finance_approved_amount = %(approved)s,
               finance_note = %(note)s,
               finance_checked = TRUE,
               finance_checked_by = %(by)s,
               finance_checked_at = NOW()
         WHERE closure_id = %(cid)s
        """,
        {
            "cid": closure_id,
            "approved": approved_amt,
            "note": note,
            "by": finance_email,
            "n50": counts[50_000],
            "n25": counts[25_000],
            "n10": counts[10_000],
            "n5": counts[5_000],
            "n1": counts[1_000],
            "n05": counts[500],
            "n025": counts[250],
        },
    )


# ─────────────────────────── UI ───────────────────────────────
def reconcile_shifts_tab():
    st.subheader("💳 Reconcile Cashier Shifts")

    finance_email = st.session_state.get("user_email", "finance@local")
    pending_df = fetch_pending()

    if pending_df.empty:
        st.success("No pending shifts.")
    else:
        st.info(f"{len(pending_df)} shift(s) awaiting approval.")
        for _, row in pending_df.iterrows():
            with st.expander(
                f"{row.cashier} — shift ended {row.shift_end:%d %b %H:%M}"
            ):
                a, b, c = st.columns(3)
                a.metric("System total", f"{row.system_total:,.0f}")
                b.metric("Cashier counted", f"{row.cash_total:,.0f}")
                c.metric("Δ", f"{row.discrepancy:+,.0f}", delta_color="inverse")

                # ───────── edit / approve form ──────────
                with st.form(f"finance_edit_{row.closure_id}"):
                    st.markdown("##### Finance bill count")
                    cols = st.columns(len(DENOMS))
                    counts = {}
                    for idx, denom in enumerate(DENOMS):
                        default = int(row[f"cnt_{denom}"])
                        counts[denom] = cols[idx].number_input(
                            f"{denom:,}",
                            min_value=0,
                            value=default,
                            step=1,
                            key=f"{denom}_{row.closure_id}",
                        )

                    approved_total = sum(d * n for d, n in counts.items())
                    st.markdown(f"**Calculated total:** {approved_total:,.0f} IQD")

                    note = st.text_area("Finance note (optional)",
                                        key=f"note_{row.closure_id}")

                    if st.form_submit_button("✅ Save & Approve"):
                        update_with_finance(
                            int(row.closure_id),
                            counts,
                            approved_total,
                            note,
                            finance_email,
                        )
                        st.success("Shift approved.")
                        st.rerun()

    # ───────── recently approved (7 days) ─────────
    with st.expander("✅ Recently approved (last 7 days)"):
        df = fetch_recent()
        if df.empty:
            st.write("None.")
        else:
            show = df[
                [
                    "cashier",
                    "shift_end",
                    "cash_total",
                    "finance_approved_amount",
                    "finance_checked_by",
                    "finance_checked_at",
                ]
            ].rename(
                columns={
                    "cashier": "Cashier",
                    "shift_end": "Ended",
                    "cash_total": "Counted",
                    "finance_approved_amount": "Approved",
                    "finance_checked_by": "By",
                    "finance_checked_at": "When",
                }
            )
            st.dataframe(show, use_container_width=True, hide_index=True)


# Stand-alone dev entry
if __name__ == "__main__":
    st.set_page_config(page_title="Reconcile", layout="wide")
    reconcile_shifts_tab()
