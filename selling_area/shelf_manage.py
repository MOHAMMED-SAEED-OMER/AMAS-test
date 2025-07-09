# selling_area/shelf_manage.py
import streamlit as st
import pandas as pd
from selling_area.shelf_handler import ShelfHandler


def shelf_manage_tab() -> None:
    """
    Admin page for viewing / editing `shelfthreshold` and `shelfaverage`.

    • Section 1 – lets you batch-fill items whose values are currently NULL.
    • Section 2 – lets you tweak one already-configured item at a time.
    """

    # ──────────────────────────────────────────────────────────
    # helpers
    # ──────────────────────────────────────────────────────────
    def _apply_update(h: ShelfHandler, item_id: int, thr: int, avg: int) -> bool:
        """
        Try to persist the new values using whatever method the
        current ShelfHandler implementation provides.

        Returns True on success, False otherwise.
        """
        possible = [
            "update_shelf_settings",      # what the UI expects
            "set_shelf_settings",
            "save_shelf_settings",
            "set_threshold_average",
            "update_item",                # accepts kwargs dict?
        ]
        for m in possible:
            if hasattr(h, m):
                fn = getattr(h, m)
                try:
                    if m == "update_item":
                        # assume signature: update_item(item_id, **fields)
                        fn(item_id, shelfthreshold=thr, shelfaverage=avg)
                    else:
                        fn(item_id, thr, avg)
                    return True
                except TypeError:
                    # signature mismatch – keep trying with the next name
                    continue
        return False

    # ──────────────────────────────────────────────────────────
    # data
    # ──────────────────────────────────────────────────────────
    st.subheader("⚙️ Shelf-management settings")

    shelf_handler = ShelfHandler()
    all_items     = shelf_handler.get_all_items()

    missing_items = all_items[
        all_items["shelfthreshold"].isna() | all_items["shelfaverage"].isna()
    ]
    editable_items = all_items[
        all_items["shelfthreshold"].notna() & all_items["shelfaverage"].notna()
    ]

    # =========================================================
    # 1) BATCH-EDIT ITEMS THAT ARE MISSING VALUES
    # =========================================================
    st.markdown("### ❗ Items missing shelf threshold / average")

    if missing_items.empty:
        st.success("✅ No items are missing shelf settings.")
    else:
        st.warning("These items do not have a threshold or average set:")

        # Prepare an editable copy (replace NaN with 0 for input safety)
        missing_editable = missing_items.copy()
        missing_editable["shelfthreshold"] = (
            missing_editable["shelfthreshold"].fillna(0).astype(int)
        )
        missing_editable["shelfaverage"] = (
            missing_editable["shelfaverage"].fillna(0).astype(int)
        )

        st.markdown(
            "*Edit the cells below and click **Update all missing items** to save.*"
        )

        edited_df = st.data_editor(
            missing_editable[
                ["itemid", "itemname", "shelfthreshold", "shelfaverage"]
            ],
            num_rows="dynamic",
            use_container_width=True,
            key="missing_thresholds_editor",
            label="Items without shelf settings",   # non-empty label for a11y
        )

        if st.button("💾 Update all missing items"):
            updated = 0
            for _, row in edited_df.iterrows():
                ok = _apply_update(
                    shelf_handler,
                    int(row["itemid"]),
                    int(row["shelfthreshold"]),
                    int(row["shelfaverage"]),
                )
                if ok:
                    updated += 1

            if updated:
                st.success(f"✅ Updated shelf settings for {updated} item(s).")
            else:
                st.error(
                    "❌ Could not find a method in `ShelfHandler` to apply the changes."
                )
            st.rerun()

    st.divider()

    # =========================================================
    # 2) EDIT A SINGLE ALREADY-CONFIGURED ITEM
    # =========================================================
    st.markdown("### ✏️ Edit shelf threshold & average for one item")

    if editable_items.empty:
        st.info(
            "No items have a threshold / average yet. "
            "Use the section above to initialise them first."
        )
        return

    item_names = editable_items["itemname"].tolist()
    selected_item = st.selectbox(
        "🔎 Pick an item to edit",
        item_names,
        index=0,
    )

    selected_row = editable_items.loc[
        editable_items["itemname"] == selected_item
    ].iloc[0]

    new_threshold = st.number_input(
        "Shelf threshold",
        min_value=0,
        value=int(selected_row["shelfthreshold"]),
        step=1,
    )
    new_average = st.number_input(
        "Shelf average",
        min_value=0,
        value=int(selected_row["shelfaverage"]),
        step=1,
    )

    if st.button("💾 Update selected item"):
        ok = _apply_update(
            shelf_handler,
            int(selected_row["itemid"]),
            int(new_threshold),
            int(new_average),
        )
        if ok:
            st.success(f"✅ Updated **{selected_item}**.")
            st.rerun()
        else:
            st.error(
                "❌ Update failed – `ShelfHandler` does not expose a compatible method."
            )
