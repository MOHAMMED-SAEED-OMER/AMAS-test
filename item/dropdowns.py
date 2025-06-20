import streamlit as st
from item.item_handler import ItemHandler

item_handler = ItemHandler()

def manage_dropdowns_tab():
    st.subheader("🛠️ Manage Dropdown Values")

    sections = [
        "ClassCat", "DepartmentCat", "SectionCat", "FamilyCat", "SubFamilyCat",
        "UnitType", "Packaging", "OriginCountry", "Manufacturer", "Brand"
    ]

    selected_section = st.selectbox("Select Dropdown Section", sections)

    # Display current values
    current_values = item_handler.get_dropdown_values(selected_section)
    st.write("**Current Values:**")
    st.write(current_values)

    # Bulk add new values
    st.write("---")
    st.write("**➕ Bulk Add Values:**")
    new_values_str = st.text_area(
        "Enter values to add (one per line)", 
        key=f"bulk_add_{selected_section}"
    )

    if st.button("Add Values"):
        new_values = [val.strip() for val in new_values_str.splitlines() if val.strip()]
        if new_values:
            added = []
            skipped = []
            for val in new_values:
                if val not in current_values:
                    item_handler.add_dropdown_value(selected_section, val)
                    added.append(val)
                else:
                    skipped.append(val)

            if added:
                st.success(f"✅ Added: {', '.join(added)}")
            if skipped:
                st.warning(f"⚠️ Already existed (skipped): {', '.join(skipped)}")
            st.rerun()
        else:
            st.error("❌ Please enter at least one value.")

    # Bulk delete existing values
    st.write("---")
    st.write("**🗑️ Bulk Delete Values:**")

    values_to_delete = st.multiselect(
        "Select values to delete",
        options=current_values,
        key=f"bulk_delete_{selected_section}"
    )

    if st.button("Delete Selected Values"):
        if values_to_delete:
            for val in values_to_delete:
                item_handler.delete_dropdown_value(selected_section, val)
            st.success(f"✅ Deleted: {', '.join(values_to_delete)}")
            st.rerun()
        else:
            st.error("❌ Please select at least one value to delete.")
