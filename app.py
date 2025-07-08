import streamlit as st
from inv_signin import authenticate

def _inject_sidebar_extras():
    try:
        from sidebar import extra_sidebar_elements
        extra_sidebar_elements()
    except ImportError:
        pass

st.set_page_config(page_title="Inventory Management System", layout="wide")

def main():
    authenticate()
    _inject_sidebar_extras()

    st.markdown(
        """
        ## Inventory Management System

        Use the menu on the left to navigate.  
        Pages are listed automatically based on the files in the `pages/` directory; you’ll only see the sections you have permission to access.
        """
    )

if __name__ == "__main__":
    main()
