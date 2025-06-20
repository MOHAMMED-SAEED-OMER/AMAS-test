"""
Tab: 📈 Item Profit / Margin analysis
─────────────────────────────────────
• Avg Cost (on hand) = Σ(qty × cost) / Σ(qty)  where qty comes from
  current rows in Inventory ∪ Shelf.
• Profit/Unit = SellingPrice − AvgCost
• Margin %    = Profit/Unit ÷ SellingPrice
• On‑Hand     = Σ current qty in Inventory ∪ Shelf
"""

import streamlit as st
import pandas as pd
import numpy as np
from finance.finance_handler import FinanceHandler

fh = FinanceHandler()


# ──────────────────────────────────────────────────────────────────
def _query_profit_overview() -> pd.DataFrame:
    """
    Returns itemid, itemname, selling price, on‑hand qty, avg cost,
    profit/unit and margin %.
    """
    sql = """
        WITH onhand AS (
            SELECT itemid,
                   SUM(quantity)                         AS qty,
                   SUM(quantity * cost_per_unit)::float  AS value
            FROM (
                SELECT itemid, quantity, cost_per_unit FROM inventory
                UNION ALL
                SELECT itemid, quantity, cost_per_unit FROM shelf
            ) x
            GROUP BY itemid
        )
        SELECT i.itemid,
               i.itemnameenglish          AS itemname,
               i.sellingprice::float      AS sellingprice,
               o.qty::int                 AS on_hand_qty,
               CASE WHEN o.qty > 0
                    THEN o.value / o.qty
               ELSE NULL END              AS avg_cost
        FROM   onhand o
        JOIN   item i ON i.itemid = o.itemid
        WHERE  o.qty > 0
    """
    df = fh.fetch_data(sql)
    if df.empty:
        return df

    df["profit_per_unit"] = df["sellingprice"] - df["avg_cost"]
    df["margin_pct"]      = np.where(
        df["sellingprice"] > 0,
        df["profit_per_unit"] / df["sellingprice"] * 100,
        np.nan
    )
    return df


# ──────────────────────────────────────────────────────────────────
def profit_tab():
    st.header("📈 Item Profit / Margin")

    df = _query_profit_overview()
    if df.empty:
        st.info("No on‑hand stock found."); return

    # ---------- optional search -----------------------------------
    search = st.text_input("🔍 Filter by name / barcode").strip()
    if search:
        df = df[df["itemname"].str.contains(search, case=False, na=False)]

    # ---------- presentation table --------------------------------
    df_display = df[[
        "itemname",
        "on_hand_qty",
        "avg_cost",
        "sellingprice",
        "profit_per_unit",
        "margin_pct",
    ]].rename(columns={
        "itemname":        "Item",
        "on_hand_qty":     "On‑Hand",
        "avg_cost":        "Avg Cost",
        "sellingprice":    "Sell Price",
        "profit_per_unit": "Profit/Unit",
        "margin_pct":      "Margin %",
    })

    def highlight_neg(v):
        return "color: red;" if v < 0 else ""

    st.dataframe(
        df_display.style.format({
            "Avg Cost":    "{:.2f}",
            "Sell Price":  "{:.2f}",
            "Profit/Unit": "{:.2f}",
            "Margin %":    "{:.1f} %",
        }).applymap(highlight_neg, subset=["Profit/Unit", "Margin %"]),
        use_container_width=True,
    )

    st.caption(
        "Average cost is weighted **only for units currently on hand** "
        "(Inventory + Shelf).  Profit/Unit = Sell Price − Avg Cost.  "
        "Margin % = Profit/Unit ÷ Sell Price."
    )
