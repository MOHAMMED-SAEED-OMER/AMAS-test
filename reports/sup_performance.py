# reports/sup_performance.py
import decimal
from typing import Any, Sequence

import pandas as pd
import streamlit as st

from reports.report_handler import ReportHandler

report_handler = ReportHandler()

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _find_col(cols: Sequence[str], *aliases: str, required: bool = True) -> str | None:
    """Return the first column that matches any alias (case-insensitive)."""
    lookup = {c.lower(): c for c in cols}
    for alias in aliases:
        hit = lookup.get(alias.lower())
        if hit:
            return hit
    if required:
        raise KeyError(f"Missing column (tried {aliases})")
    return None


def _to_float(x: Any) -> float:
    """Convert Decimal / int / str / None → float (fallback 0)."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return 0.0
    try:
        return float(x)
    except (ValueError, TypeError, decimal.InvalidOperation):
        return 0.0


def _pct(numerator: float, denominator: float) -> float:
    """Safe percentage (0 – 100)."""
    return (_to_float(numerator) / _to_float(denominator) * 100) if denominator else 0.0


def _format_delay(hours: Any) -> str:
    """Convert hours → 'Xd Yhr' or 'On Time'."""
    h = _to_float(hours)
    if h <= 0:
        return "On Time"
    days, rem = divmod(int(h), 24)
    return f"{days}d {rem}hr" if days else f"{rem}hr"


# ─────────────────────────────────────────────────────────────────────────────
# Main tab
# ─────────────────────────────────────────────────────────────────────────────
def sup_performance_tab() -> None:
    st.header("📊 Supplier Performance Report")

    df = report_handler.get_supplier_performance()

    if df.empty:
        st.warning("⚠️ No supplier performance data available.")
        return

    # ── resolve column names flexibly ────────────────────────────────────
    try:
        c_sup   = _find_col(df.columns, "suppliername", "supplier", "name")
        c_tot   = _find_col(df.columns, "totalorders", "orders")
        c_ot    = _find_col(df.columns, "ontimedeliveries", "on_time_deliveries")
        c_late  = _find_col(df.columns, "latedeliveries", "late_deliveries", required=False)
        c_late_avg = _find_col(df.columns, "avglatehours", "avg_late_hours", required=False)
        c_qty_ok   = _find_col(df.columns, "correctquantityorders", "qty_accuracy_orders")
        c_qty_bad  = _find_col(df.columns, "quantitymismatchorders", "qty_mismatch_orders", required=False)
    except KeyError as err:
        st.error(f"Dataset is missing a required column: {err}")
        st.dataframe(df)        # show raw data to aid debugging
        return

    # ── compute metrics ────────────────────────────────────────────────
    metrics = df.copy()

    metrics["On-Time Delivery Rate"] = [
        _pct(ot, tot) for ot, tot in zip(metrics[c_ot], metrics[c_tot])
    ]
    metrics["Quantity Accuracy Rate"] = [
        _pct(ok, tot) for ok, tot in zip(metrics[c_qty_ok], metrics[c_tot])
    ]
    if c_late_avg:
        metrics["Avg Late Time"] = metrics[c_late_avg].apply(_format_delay)
    else:
        metrics["Avg Late Time"] = "—"

    # ── build display table ────────────────────────────────────────────
    display = pd.DataFrame(
        {
            "Supplier": metrics[c_sup],
            "Total Orders": metrics[c_tot],
            "On-Time Deliveries": metrics[c_ot],
            "Late Deliveries": metrics.get(c_late, pd.Series("—")),
            "Avg Late Time": metrics["Avg Late Time"],
            "Qty Mismatch Orders": metrics.get(c_qty_bad, pd.Series("—")),
            "On-Time Delivery Rate": metrics["On-Time Delivery Rate"],
            "Quantity Accuracy Rate": metrics["Quantity Accuracy Rate"],
        }
    )

    st.subheader("📋 Supplier Performance Overview")
    st.dataframe(
        display.style.format(
            {
                "On-Time Delivery Rate": "{:.1f} %",
                "Quantity Accuracy Rate": "{:.1f} %",
            }
        ),
        use_container_width=True,
    )

    # ── highlight under-performers ──────────────────────────────────────
    underperf = display[
        (display["On-Time Delivery Rate"] < 80) | (display["Quantity Accuracy Rate"] < 80)
    ]
    if not underperf.empty:
        st.subheader("⚠️ Under-performing Suppliers")
        st.dataframe(
            underperf[["Supplier", "On-Time Delivery Rate", "Quantity Accuracy Rate"]],
            use_container_width=True,
        )

    st.success("✅ Report generated successfully!")
