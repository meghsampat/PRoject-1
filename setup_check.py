"""Minimal environment check; analytics prototype is not implemented yet."""
import sys
import streamlit as st

st.set_page_config(page_title="FMCG Setup Check")
st.title("FMCG Product Intelligence System")
st.success("Streamlit is running locally.")
st.warning("Setup check only. Analytics, agents, and Judge are pending.")
st.caption(f"Python {sys.version.split()[0]} — project target: Python 3.11")

