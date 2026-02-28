"""
Simple password gate for Streamlit apps.
Password is set in .streamlit/secrets.toml or .env — never hardcoded.

Usage (add to top of any Streamlit app, after set_page_config):
    from dashboard.auth import require_password
    require_password()
"""

import os
import streamlit as st


def require_password():
    """
    Password gate — TEMPORARILY DISABLED for testing/deployment.
    Re-enable by restoring the full implementation below.
    """
    return  # ← remove this line to re-enable the password gate

    # Get password from secrets or env
    password = None
    try:
        password = st.secrets.get("auth", {}).get("password")
    except Exception:
        pass
    if not password:
        password = os.getenv("DASHBOARD_PASSWORD", "")

    # No password configured → run open (local dev)
    if not password:
        return

    # Already authenticated this session
    if st.session_state.get("authenticated"):
        return

    # Show password gate
    st.title("🔒 Versuni MS Wave III")
    st.caption("Enter the access password to continue.")
    col1, col2 = st.columns([2, 3])
    with col1:
        entered = st.text_input("Password", type="password", key="pw_input")
        if st.button("Enter", type="primary"):
            if entered == password:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Incorrect password.")
    st.stop()
