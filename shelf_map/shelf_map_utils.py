# shelf_map/shelf_map_utils.py
import streamlit as st


def shelf_selector(locs: list[dict]) -> str | None:
    """
    Render a searchable dropdown.  
    Returns the chosen `locid`, or `None` if "Show all shelves".
    """
    if not locs:
        st.warning("No shelf locations found.")
        return None

    options = [f"{l['locid']} – {l['label']}" for l in locs]
    options.insert(0, "🔍 Show all shelves")

    current = st.session_state.get("shelfmap_highlight")
    if isinstance(current, list):
        current = current[0] if current else None
    index = 0
    if current:
        for i, opt in enumerate(options):
            if opt.startswith(current):
                index = i
                break

    choice = st.selectbox(
        "Select a shelf (type to search):",
        options,
        index=index,
        key="shelfmap_selector",
    )
    return None if choice == options[0] else choice.split()[0]


def item_locator(
    handler,
    name_container=st,
    barcode_container=st,
) -> tuple[list[str] | None, int | None, bool]:
    """Render inputs to locate an item and return matching ``locid``\s.

    Parameters
    ----------
    handler : ShelfMapHandler
        Used to fetch item and location information from the database.
    name_container : st.delta_generator.DeltaGenerator, optional
        Container for the item name ``selectbox``.
    barcode_container : st.delta_generator.DeltaGenerator, optional
        Container for the barcode ``text_input``.

    Returns
    -------
    tuple
        ``(locids, itemid, queried)`` where ``locids`` is a list of matching
        location ids or ``None``, ``itemid`` is the selected item id (if any)
        and ``queried`` indicates whether the user entered a search.
    """

    df = handler.get_items_on_shelf()
    if df.empty:
        st.info("No items found on shelf.")
        return None, None, False

    lookup = dict(zip(df.itemname, df.itemid))
    names = ["🔍 Type item name"] + list(lookup.keys())

    with name_container:
        item_choice = st.selectbox(
            "Find item location by name:",
            names,
            key="item_name_selector",
        )

    with barcode_container:
        barcode = st.text_input(
            "Find item by barcode:", key="item_barcode_input"
        )

    locids: list[str] = []
    selected_id = None

    if item_choice and item_choice != names[0]:
        selected_id = int(lookup[item_choice])
        locs = handler.get_locations_by_itemid(selected_id)
        if not locs.empty:
            locids.extend(locs.loc[:, "locid"].astype(str).tolist())

    if barcode:
        locs = handler.get_locations_by_barcode(barcode.strip())
        if not locs.empty:
            for loc in locs.loc[:, "locid"].astype(str).tolist():
                if loc not in locids:
                    locids.append(loc)
        if selected_id is None:
            selected_id = handler.get_itemid_by_barcode(barcode.strip())

    queried = bool(barcode) or (item_choice and item_choice != names[0])
    return (locids if locids else None), selected_id, queried
