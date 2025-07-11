# item/add_item.py  – handles binary images for MySQL
from __future__ import annotations

import mysql.connector            # for Binary()
import streamlit as st
import pandas as pd

from item.item_handler import ItemHandler

item_handler = ItemHandler()

# ────────────────────────────────────────────────────────────────
# Cached dropdown lists (refresh every 3 min)
# ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=180, show_spinner=False)
def load_dropdowns() -> dict[str, list[str]]:
    mapping = {
        "Class Category":      "ClassCat",
        "Department Category": "DepartmentCat",
        "Section Category":    "SectionCat",
        "Family Category":     "FamilyCat",
        "Sub-Family Category": "SubFamilyCat",
        "Unit Type":           "UnitType",
        "Packaging":           "Packaging",
        "Origin Country":      "OriginCountry",
        "Manufacturer":        "Manufacturer",
        "Brand":               "Brand",
    }
    return {
        label: item_handler.get_dropdown_values(section)
        for label, section in mapping.items()
    }

# ────────────────────────────────────────────────────────────────
# Cached supplier list (refresh every 3 min)
# ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=180, show_spinner=False)
def load_suppliers() -> pd.DataFrame:
    return item_handler.get_suppliers()

# ────────────────────────────────────────────────────────────────
# Main tab
# ────────────────────────────────────────────────────────────────
def add_item_tab() -> None:
    st.header("➕ Add New Item")

    # Cached look-ups (fast after first run)
    dd           = load_dropdowns()
    suppliers_df = load_suppliers()
    supplier_names = suppliers_df["suppliername"].tolist()

    # Required labels
    required = {
        "Item Name (English)",
        "Class Category",
        "Shelf Life",
        "Threshold",
        "Average Required",
    }
    req = lambda lbl: f"{lbl} *" if lbl in required else lbl

    # ─────────── FORM ───────────
    with st.form("add_item_form", clear_on_submit=True):
        # Names
        item_name_en = st.text_input(req("Item Name (English)"))
        item_name_ku = st.text_input("Item Name (Kurdish)")

        # Categories
        class_cat      = st.selectbox(req("Class Category"),      [""] + dd["Class Category"])
        department_cat = st.selectbox("Department Category",      [""] + dd["Department Category"])
        section_cat    = st.selectbox("Section Category",         [""] + dd["Section Category"])
        family_cat     = st.selectbox("Family Category",          [""] + dd["Family Category"])
        subfamily_cat  = st.selectbox("Sub-Family Category",      [""] + dd["Sub-Family Category"])

        # Numeric
        shelf_life       = st.number_input(req("Shelf Life"),       min_value=0)
        threshold        = st.number_input(req("Threshold"),        min_value=0)
        average_required = st.number_input(req("Average Required"), min_value=0)

        # Optional attributes
        origin_country = st.selectbox("Origin Country", [""] + dd["Origin Country"])
        manufacturer   = st.selectbox("Manufacturer",   [""] + dd["Manufacturer"])
        brand          = st.selectbox("Brand",          [""] + dd["Brand"])

        # Barcodes & packaging
        barcode        = st.text_input("Barcode")
        packet_barcode = st.text_input("Packet Barcode")
        carton_barcode = st.text_input("Carton Barcode")
        unit_type      = st.selectbox("Unit Type", [""] + dd["Unit Type"])
        packaging      = st.selectbox("Packaging", [""] + dd["Packaging"])

        # Image
        item_picture = st.file_uploader("Item Picture", type=["png", "jpg", "jpeg"])

        # Suppliers
        selected_sup_names = st.multiselect("Select Supplier(s)", supplier_names)
        selected_sup_ids   = suppliers_df[
            suppliers_df["suppliername"].isin(selected_sup_names)
        ]["supplierid"].tolist()

        # Submit
        submitted = st.form_submit_button("Add Item")

    # ─────────── After submit ───────────
    if not submitted:
        return

    # Required-field guard
    if not all([item_name_en, class_cat, shelf_life, threshold, average_required]):
        st.error("❌ Please fill in all required fields.")
        return

    # Duplicate-name guard (fast single-row query)
    if item_handler.item_name_exists(item_name_en):
        st.error("❌ An item with this English name already exists!")
        return

    # Image bytes → Binary
    pic_bytes = mysql.connector.Binary(item_picture.getvalue()) if item_picture else None

    # Assemble row
    item_data = {
        "itemnameenglish": item_name_en.strip(),
        "itemnamekurdish": item_name_ku.strip() or None,
        "classcat":        class_cat,
        "departmentcat":   department_cat or None,
        "sectioncat":      section_cat or None,
        "familycat":       family_cat or None,
        "subfamilycat":    subfamily_cat or None,
        "shelflife":       int(shelf_life),
        "threshold":       int(threshold),
        "averagerequired": int(average_required),
        "origincountry":   origin_country or None,
        "manufacturer":    manufacturer or None,
        "brand":           brand or None,
        "barcode":         barcode.strip()        or None,
        "packetbarcode":   packet_barcode.strip() or None,
        "cartonbarcode":   carton_barcode.strip() or None,
        "unittype":        unit_type or None,
        "packaging":       packaging or None,
        "itempicture":     pic_bytes,
    }

    # DB insert + supplier link
    new_id = item_handler.add_item(item_data, selected_sup_ids)
    if new_id:
        st.success("✅ Item added successfully!")
    else:
        st.error("❌ Error adding item. Please try again.")
