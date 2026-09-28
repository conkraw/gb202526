# NBME Scores
# Edit this file to change this dropdown section.
# app2627.py calls render() on every Streamlit rerun.
# The original section body is preserved below.

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


def render():
    #Title of Page with Website Links. 
    st.header("🔖 NBME")
    st.markdown("[Open OASIS Gradebook](https://oasis.pennstatehealth.net/admin/course/gradebook/)")

    # Upload exactly one Excel file
    nbme_file = st.file_uploader("Upload exactly one NBME XLSX",type=["xlsx"],accept_multiple_files=False,key="nbme")

    # Stops code if no file or if wrong file is present. 
    if not nbme_file:
        st.stop()

    # read the specific worksheet - NBME worksheet has two sheet, it will read the workbook and find the sheet that we want. 
    df_nbme = pd.read_excel(nbme_file, sheet_name="GradeBook", dtype=str)

    # rename only the nine columns you need
    rename_map_nbme = {
        "Student":                        "student_nbme",
        "Email":                          "email_nbme",
        "Username":                       "username",
        "External ID":                    "record_id",
        "Student Level":                  "student_level_nbme",
        "Location":                       "location_nbme",
        "Start Date":                     "start_date_nbme",
        "NBME Exam - Percentage Score":   "nbme",
        "NBME Exam Grade":                "grade_nbme",
        "Final Course Grade":             "final_course_grade",
    }

    # Executes Renaming
    df_nbme = df_nbme.rename(columns=rename_map_nbme)

    # keep only those nine columns, in that order
    df_nbme = df_nbme[list(rename_map_nbme.values())]

    # Rename external_id to record_id... this is your key.
    # move external_id → record_id up front 
    df_nbme = df_nbme.rename(columns={"external_id": "record_id"})
    cols = ["record_id"] + [c for c in df_nbme.columns if c != "record_id"]
    df_nbme = df_nbme[cols]

    # add REDCap repeater fields
    df_nbme["redcap_repeat_instrument"] = "nbme"
    df_nbme["redcap_repeat_instance"]   = df_nbme.groupby("record_id").cumcount() + 1

    exclude = ['student_nbme', 'email_nbme', 'username', 'student_level_nbme', 'location_nbme', 'start_date_nbme', 'grade_nbme', 'final_course_grade']
    df_nbme = df_nbme.drop(columns=exclude, errors='ignore')
    # preview + download
    st.dataframe(df_nbme, height=400)
    st.download_button("📥 Download formatted NBME XLSX → CSV",df_nbme.to_csv(index=False).encode("utf-8"),file_name="nbme_scores_formatted.csv",mime="text/csv")

