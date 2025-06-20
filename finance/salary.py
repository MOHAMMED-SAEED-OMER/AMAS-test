# finance/salary.py
import streamlit as st
from datetime import date
from finance.finance_handler import FinanceHandler

fh = FinanceHandler()


# ─────────────────────────── tab UI ──────────────────────────────
def salary_tab():
    st.header("🧾 Employee Salaries")

    # Month selector
    today = date.today()
    col_y, col_m = st.columns(2)
    year  = col_y.number_input("Year", 2000, 2100, today.year, 1)
    month = col_m.selectbox(
        "Month", list(range(1, 13)),
        format_func=lambda m: date(1900, m, 1).strftime("%B"),
        index=today.month - 1,
    )

    # Load status via FinanceHandler
    status_df = fh.get_salary_month_status(int(year), int(month))
    if status_df.empty:
        st.info("No active employees found."); return

    st.dataframe(
        status_df.rename(columns={
            "fullname":     "Employee",
            "expected":     "Salary",
            "paid_so_far":  "Paid",
            "outstanding":  "Outstanding",
        }).style.format({
            "Salary":      "{:,.2f}",
            "Paid":        "{:,.2f}",
            "Outstanding": "{:,.2f}",
        }).applymap(lambda v: "color: red;" if isinstance(v, (int, float)) and v > 0 else ""),
        use_container_width=True,
    )

    # Payment form
    st.markdown("---")
    st.subheader("💵 Record Salary Payment")

    emp_lookup = dict(zip(status_df.fullname, status_df.employeeid))
    sel_emp = st.selectbox("Employee", list(emp_lookup.keys()))

    if sel_emp:
        outstanding = float(
            status_df.loc[status_df.fullname == sel_emp, "outstanding"].iloc[0]
        )
                # ----- payment form widgets (unique keys) ------------------------
        unique = f"{sel_emp}_{year}_{month}"          # suffix for keys

        col1, col2, col3, col4 = st.columns([2, 1, 1, 2])
        amount = col1.number_input(
            "Amount",
            min_value=0.01,
            max_value=outstanding if outstanding > 0 else None,
            step=0.01,
            format="%.2f",
            key=f"sal_amount_{unique}",
        )
        pay_date = col2.date_input(
            "Pay date", value=today, key=f"sal_date_{unique}"
        )
        method = col3.selectbox(
            "Method", ["Cash", "Bank", "Other"], key=f"sal_method_{unique}"
        )
        notes = col4.text_input("Notes", key=f"sal_notes_{unique}")

        if st.button("💾 Save payment", key=f"sal_save_btn_{unique}"):
            if amount <= 0:
                st.error("Enter a positive amount.")
                st.stop()

            fh.record_salary_payment(
                employee_id=emp_lookup[sel_emp],
                period_year=int(year),
                period_month=int(month),
                pay_date=pay_date,
                amount=amount,
                method=method,
                notes=notes,
            )
            st.success("Payment recorded.")
            st.rerun()


# manual test
if __name__ == "__main__":
    salary_tab()
