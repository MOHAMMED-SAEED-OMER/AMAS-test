import streamlit as st

# use relative (“.”) imports so we don’t collide with the keyword *return*
from returns.add_return import return_tab   # ✅ Updated here
from returns.track_return import track_returns_tab

def main_return_page() -> None:
    st.title("↩️ Supplier Returns")

    tabs = st.tabs(["➕ New Return", "📋 Track Returns"])
    with tabs[0]:
        return_tab()
    with tabs[1]:
        track_returns_tab() 

if __name__ == "__main__":
    main_return_page()
