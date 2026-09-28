from __future__ import annotations
import re
import streamlit as st
import pandas as pd
from io import BytesIO
from docx import Document
import pytz

import re
from dataclasses import dataclass
from io import BytesIO
from typing import Iterable
from urllib.parse import quote_plus


st.set_page_config(
    page_title="REDCap Formatter",
    layout="wide"
)
# choose which instrument you want to format
instrument = st.sidebar.selectbox("Select instrument", ["OASIS Evaluation", "Checklist Entry", "Preceptor Matching", "NBME Scores", "Roster_HMC", "Roster_KP", "Roster_Updater","Oasis Reminder","Session Feedback Link Creator","Session Feedback Summary Creator"])

# ---------------------------------------------------------
# Hide general REDCap header for selected instruments
# ---------------------------------------------------------

HIDE_MAIN_HEADER_FOR = {
    "Session Feedback Link Creator",
    "Session Feedback Summary Creator",
}

if instrument not in HIDE_MAIN_HEADER_FOR:

    st.title("🔄 REDCap Instruments Formatter")

    st.markdown(
        "[Open REDCap Data Import]"
        "(https://redcap.ctsi.psu.edu/redcap_v15.5.35/index.php?"
        "pid=19389&route=DataImportController:index)"
    )




# Each dropdown section lives in its own file in the instruments folder.
# Select the matching module and call render() on every Streamlit rerun.
# Imports alone would not rerun a section after the first visit.
from importlib import import_module

INSTRUMENT_MODULES = {
    'OASIS Evaluation': 'oasis_evaluation',
    'Checklist Entry': 'checklist_entry',
    'Preceptor Matching': 'preceptor_matching',
    'NBME Scores': 'nbme_scores',
    'Roster_HMC': 'roster_hmc',
    'Roster_KP': 'roster_kp',
    'Roster_Updater': 'roster_updater',
    'Oasis Reminder': 'oasis_reminder',
    'Session Feedback Link Creator': 'session_feedback_link_creator',
    'Session Feedback Summary Creator': 'session_feedback_summary_creator',
}

selected_module = import_module(f"instruments.{INSTRUMENT_MODULES[instrument]}")
selected_module.render()
