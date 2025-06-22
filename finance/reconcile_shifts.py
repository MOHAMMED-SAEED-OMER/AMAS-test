"""
Finance ▸ Reconcile Shifts  –  version with EDIT + APPROVE
"""
from __future__ import annotations
import streamlit as st
from datetime import datetime
from db_handler import DatabaseManager

_db = DatabaseManager()
DENOMS = [50_000, 25_000, 10_000, 5_000, 1_000, 500, 250]


# ──────────────────── DB helper ─────────────────────
def fetch_pending():
    return _db.fetch_data(
        "SELECT * FROM cashier_shift_closure "
        "WHERE finance_checked = FALSE "
        "ORDER BY shift_end DESC"
    )


def fetch_recent(days=7):
    return _db.fetch_data(
        "SELECT * FROM cashier_shift_closure "
        "WHERE finance_checked = TRUE "
        "  AND finance_checked_at >= CURRENT_DATE - %s::INT "
        "ORDER  BY finance_checked_at DESC",
        (days,),
    )


def update_with_finance(row_id: int, counts: dict[int, int],
                        approved: float, note: str, email: str):
    _db.execute_command(
        """
        UPDATE cashier_shift_closure
           SET
             finance_cnt_50000 = %(n50)s,
             finance_cnt_25000 = %(n25)s,
             finance_cnt_10000 = %(n10)s,
             finance_cnt_5000  = %(n5)s,
             finance_cnt_1000  = %(n1)s,
             finance_cnt_500   = %(n05)s,
             finance_cnt_250   = %(n025)s,
             finance_approved_amount = %(approved)s,
             finance_note      = %(note)s,
             finance_checked   = TRUE,
             finance_checked_by  = %(by)s,
             finance_checked_at  = NOW()
         WHERE closure_id = %(cid)s
        """,
        {
            "cid": row_id, "approved": approved, "note": note, "by": email,
            "n50": counts[50_000], "n25": counts[25_000], "n10": counts[10_000],
            "n5": counts[5_000], "n1": counts[1_000],
            "n05": counts[500], "n025": counts[250],
        },
    )


# ──────────────────── UI ────────────────────────────
def reconcile_shifts_tab():
    st.subheader("💳 Reconcile Cashier Shifts")

    user_email = st.session_state.get("user_email", "finance@local")
    pending = fetch_pending()

    if pending.empty:
        st.success("No pending shifts.")
    else:
        st.info(f"{len(pending)} shift(s) awaiting approval.")
        for _, row in pending.iterrows():
            exp = st.expander(
                f"{row.cashier} — ended {row.shift_end:%d-%b %H:%M}"
            )

            with exp:
                col1, col2, col3 = st.columns(3)
                col1.metric("System total", f"{row.system_total:,.0f}")
                col2.metric("Cashier counted", f"{row.cash_total:,.0f}")
                col3.metric("Δ", f"{row.discrepancy:+,.0f}",
                            delta_color="inverse")

                # ── EDIT FORM ──────────────────────────────────────
                with st.form(f"edit_form_{row.closure_id}", clear_on_submit=False):
                    st.markdown("##### Finance count (edit if needed)")
                    c = st.columns(len(DENOMS))
                    counts = {}
                    for i, d in enumerate(DENOMS):
                        default = int(row[f"cnt_{d}"])
                        counts[d] = c[i].number_input(
                            f"{d:,}", min_value=0, value=default, step=1,
                            key=f"cnt_{d}_{row.closure_id}",
                        )

                    approved_total = sum(d * n for d, n in counts.items())
                    st.write(f"**Calculated total:** {approved_total:,.0f} IQD")

                    note = st.text_area(
                        "Finance note (optional)",
                        key=f"note_{row.closure_id}",
                    )

                    submitted = st.form_submit_button("✅ Save & Approve")
                    if submitted:
                        update_with_finance(
                            int(row.closure_id),
                            counts,
                            approved_total,
                            note,
                            user_email,
                        )
                        st.success("Shift approved.")
                        st.experimental_rerun()

    # ───── recently approved
    with st.expander("✅ Recently approved (7 days)"):
        df = fetch_recent()
        if df.empty:
            st.write("None.")
        else:
            show = df[[
                "cashier", "shift_end",
                "cash_total", "finance_approved_amount",
                "finance_checked_by", "finance_checked_at",
            ]].rename(columns={
                "cashier": "Cashier",
                "shift_end": "Ended",
                "cash_total": "Cashier",
                "finance_approved_amount": "Finance",
                "finance_checked_by": "By",
                "finance_checked_at": "When",
            })
            st.dataframe(show, use_container_width=True, hide_index=True)


# Dev entry
if __name__ == "__main__":
    st.set_page_config("Reconcile", layout="wide")
    reconcile_shifts_tab()
