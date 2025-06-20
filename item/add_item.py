# item/add_item.py
import streamlit as st
from item.item_handler import ItemHandler

item_handler = ItemHandler()

# ────────────────────────────────────────────────────────────────
# 1.  Cached dropdown lists (refresh every 10 min)
# ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner=False)
def load_dropdowns():
    # Mapping dropdown label → DB section name
    dropdown_fields = {
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
        lbl: item_handler.get_dropdown_values(db_sec)
        for lbl, db_sec in dropdown_fields.items()
    }

dropdown_values = load_dropdowns()

# ────────────────────────────────────────────────────────────────
def add_item_tab():
    st.header("➕ Add New Item")

    required = ["Item Name (English)", "Class Category",
                "Shelf Life", "Threshold", "Average Required"]

    # HTML bullet for required fields
    def req(label):
        return f"{label} *" if label in required else label

    # ─────────── FORM ───────────
    with st.form("add_item_form", clear_on_submit=True):
        # Text inputs
        item_name_en = st.text_input(req("Item Name (English)"))
        item_name_ku = st.text_input("Item Name (Kurdish)")

        class_cat = st.selectbox(
            req("Class Category"), [""] + dropdown_values["Class Category"]
        )

        department_cat = st.selectbox(
            "Department Category", [""] + dropdown_values["Department Category"]
        )
        section_cat = st.selectbox(
            "Section Category", [""] + dropdown_values["Section Category"]
        )
        family_cat = st.selectbox(
            "Family Category", [""] + dropdown_values["Family Category"]
        )
        subfamily_cat = st.selectbox(
            "Sub-Family Category", [""] + dropdown_values["Sub-Family Category"]
        )

        shelf_life       = st.number_input(req("Shelf Life"), min_value=0)
        threshold        = st.number_input(req("Threshold"), min_value=0)
        average_required = st.number_input(req("Average Required"), min_value=0)

        origin_country = st.selectbox(
            "Origin Country", [""] + dropdown_values["Origin Country"]
        )
        manufacturer = st.selectbox(
            "Manufacturer", [""] + dropdown_values["Manufacturer"]
        )
        brand = st.selectbox(
            "Brand", [""] + dropdown_values["Brand"]
        )

        barcode    = st.text_input("Barcode")
        packet_barcode = st.text_input("Packet Barcode")
        carton_barcode = st.text_input("Carton Barcode")
        unit_type  = st.selectbox(
            "Unit Type", [""] + dropdown_values["Unit Type"]
        )
        packaging  = st.selectbox(
            "Packaging", [""] + dropdown_values["Packaging"]
        )

        item_picture = st.file_uploader("Item Picture", type=["jpg", "jpeg", "png"])

        # Supplier multiselect
        suppliers_df      = item_handler.get_suppliers()
        supplier_names    = suppliers_df["suppliername"].tolist()
        selected_sup_names = st.multiselect("Select Supplier(s)", supplier_names)
        selected_sup_ids   = suppliers_df[
            suppliers_df["suppliername"].isin(selected_sup_names)
        ]["supplierid"].tolist()

        # ── Submit button ──
        submitted = st.form_submit_button("Add Item")

    # ─────────── After submit ───────────
    if not submitted:
        return

    # Validate required fields
    if not all([item_name_en, class_cat, shelf_life, threshold, average_required]):
        st.error("❌ Please fill in all required fields.")
        return

    # Duplicate item check
    existing = item_handler.get_items()
    if item_name_en.strip().lower() in (
        existing["itemnameenglish"].str.strip().str.lower().values
    ):
        st.error("❌ An item with this English name already exists!")
        return

    # Prepare picture bytes
    pic_bytes = item_picture.getvalue() if item_picture else None

    # Build item dict
    item_data = {
        "itemnameenglish": item_name_en.strip(),
        "itemnamekurdish": item_name_ku.strip(),
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
        "barcode":        barcode.strip() or None,
        "packetbarcode":  packet_barcode.strip() or None,
        "cartonbarcode":  carton_barcode.strip() or None,
        "unittype":        unit_type or None,
        "packaging":       packaging or None,
        "itempicture":     pic_bytes,
    }

    # Insert & link suppliers
    new_id = item_handler.add_item(item_data, selected_sup_ids)
    if new_id:
        st.success("✅ Item added successfully!")
    else:
        st.error("❌ Error adding item. Please try again.")
