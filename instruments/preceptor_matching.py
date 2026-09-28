# Preceptor Matching
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
    st.header("🔖 Preceptor Matching")
    st.markdown("[OASIS Preceptor Matching](https://oasis.pennstatehealth.net/admin/course/e_manage/manage_evaluators.html)")

    # upload exactly one CSV
    preceptor_file = st.file_uploader(
        "Upload exactly one Preceptor Matching CSV",
        type=["csv"],
        accept_multiple_files=False,
        key="preceptor"
    )
    if not preceptor_file:
        st.stop()

    # read
    df_pmx = pd.read_csv(preceptor_file, dtype=str)

    # drop the unwanted Delete column
    if "Delete" in df_pmx.columns:
        df_pmx = df_pmx.drop(columns=["Delete"])

    # rename only the REDCap-friendly columns
    rename_map = {
        "Start Date":                    "start_date",
        "End Date":                      "end_date",
        "Location":                      "location",
        "Faculty Name":                  "faculty_name",
        "Faculty Username":              "faculty_username",
        "Faculty External ID":           "faculty_external_id",
        "Faculty Email":                 "faculty_email",
        "Type of Association":           "type_of_association",
        "Student Name":                  "student_name",
        "Student Username":              "student_username",
        "Student External ID":           "record_id",
        "Student Email":                 "student_email",
        "Evaluation Period Start Date":  "eval_period_start_date",
        "Evaluation Period End Date":    "eval_period_end_date",
        "Classification":                "classification",
        "Student Activity":              "student_activity1",
        "Manual Evaluations":            "manual_evaluations",
    }
    df_pmx = df_pmx.rename(columns=rename_map)

    # keep only those columns, in that exact order
    df_pmx = df_pmx[list(rename_map.values())]

    # move record_id to front
    df_pmx = df_pmx[["record_id"] + [c for c in df_pmx.columns if c != "record_id"]]

    # drop columns you do not want
    df_pmx = df_pmx.drop(columns=[
        "start_date",
        "end_date",
        "location",
        "student_name",
        "student_username",
        "student_email"
    ])

    # normalize manual_evaluations to one per row
    df_pmx["manual_evaluations"] = (
        df_pmx["manual_evaluations"]
        .fillna("")
        .str.split("|")
    )

    df_pmx = df_pmx.explode("manual_evaluations")

    df_pmx["manual_evaluations"] = (
        df_pmx["manual_evaluations"]
        .fillna("")
        .str.lstrip("*")
        .str.strip()
    )

    # remove blank rows
    df_pmx = df_pmx[df_pmx["manual_evaluations"] != ""]

    # drop unwanted categories
    to_drop = ["Clinical Teaching Eval", "Mid-Cycle Feedback"]
    df_pmx = df_pmx[~df_pmx["manual_evaluations"].isin(to_drop)]

    # get all unique manual_evaluations values
    opts = sorted(df_pmx["manual_evaluations"].dropna().unique().tolist())

    # multiselect defaulting to all
    selected = st.multiselect(
        "Filter by manual_evaluations:",
        options=opts,
        default=opts
    )

    # filter the DataFrame
    df_pmx = df_pmx[df_pmx["manual_evaluations"].isin(selected)]

    # NOW assign REDCap repeater fields
    df_pmx["redcap_repeat_instrument"] = "preceptor_matching"
    df_pmx["redcap_repeat_instance"] = df_pmx.groupby("record_id").cumcount() + 1

    # optional: reorder so repeat fields are near the front
    front_cols = ["record_id", "redcap_repeat_instrument", "redcap_repeat_instance"]
    remaining_cols = [c for c in df_pmx.columns if c not in front_cols]
    df_pmx = df_pmx[front_cols + remaining_cols]

    # preview + download
    st.dataframe(df_pmx, height=400)
    st.download_button(
        "📥 Download formatted Preceptor Matching CSV",
        df_pmx.to_csv(index=False).encode("utf-8"),
        file_name="preceptor_matching_formatted.csv",
        mime="text/csv",
    )
    


