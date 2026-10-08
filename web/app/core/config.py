import os

THRESHOLD = 85.0       # minimum attendance %
WARNING_BAND = 5.0     # 85-90% counts as "close to" the threshold
WEAK_MARK = 40.0       # latest test below this = weak
FALL_DROP = 10.0       # drop of this many marks = falling
MAX_CALLS_PER_RUN = 3  # cap on real phone calls per analysis run


def secret(name: str, default: str = "") -> str:
    """Read a setting from env vars first, then Streamlit secrets."""
    value = os.getenv(name)
    if value:
        return value
    try:
        import streamlit as st
        return str(st.secrets.get(name, default) or default)
    except Exception:
        return default
