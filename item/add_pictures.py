import streamlit as st
from item.item_handler import ItemHandler

item_handler = ItemHandler()

def add_pictures_tab():
    """Tab for adding pictures to items without images."""
    st.header("🖼️ Add Pictures to Items")

    # ✅ Fetch items that don't have pictures
    items_df = item_handler.get_items_without_pictures()

    if items_df.empty:
        st.success("✅ All items have pictures!")
        return

    # ✅ Let the user select an item
    item_options = dict(zip(items_df["itemnameenglish"], items_df["itemid"]))
    selected_item_name = st.selectbox("Select an item to add a picture", list(item_options.keys()))
    selected_item_id = item_options[selected_item_name]

    # ✅ File uploader for image
    uploaded_picture = st.file_uploader("📤 Upload Picture", type=["jpg", "jpeg", "png"])

    if uploaded_picture and st.button("📥 Save Picture"):
        # Convert the uploaded file into binary
        picture_data = uploaded_picture.read()

        # ✅ Update item picture in the database
        item_handler.update_item_picture(selected_item_id, picture_data)

        st.success(f"✅ Picture added for {selected_item_name}!")
        st.rerun()
