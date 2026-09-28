# Checklist Entry
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
    st.header("🔖 Checklist Entry Merger")
    st.markdown("[Open Clinical Encounters Requirement](https://oasis.pennstatehealth.net/admin/course/experience_requirement/view_distribution_setup.html)")

    uploaded = st.file_uploader("Upload exactly one checklist CSVs",type="csv",accept_multiple_files=True,key="clist")
    if not uploaded:
        st.stop()

    # Read + concat
    dfs = [pd.read_csv(f, dtype=str) for f in uploaded]
    df_cl = pd.concat(dfs, ignore_index=True, sort=False)

    # Rename only your 22 columns
    rename_map = {
        "Student name":           "student_name",
        "External ID":            "external_id",
        "Email":                  "email",
        "Start Date":             "start_date",
        "Location":               "location_cl",
        "Checklist":              "checklist",
        "Checklist status":       "checklist_status",
        "Item":                   "item",
        "Item status":            "item_status",
        "Original/Copy":          "originalcopy",
        "Signed By":              "signed_by",
        "Time Signed":            "time_signed",
        "Verified By":            "verified_by",
        "Verification Comments":  "verification_comments",
        "Verified Date":          "verified_date",
        "Time entered":           "time_entered",
        "Date":                   "date",
        "Times observed":         "times_observed",
        "Is proficient":          "is_proficient",
        "Needs Practice":         "needs_practice",
        "Comments":               "comments",
    }
    df_cl = df_cl.rename(columns=rename_map)

    # Select + reorder
    target = list(rename_map.values())
    df_cl = df_cl[target]

    # Move external_id → record_id up front
    df_cl = df_cl.rename(columns={"external_id": "record_id"})
    cols = ["record_id"] + [c for c in df_cl.columns if c != "record_id"]
    df_cl = df_cl[cols]

    # Add REDCap repeater
    df_cl["redcap_repeat_instrument"] = "checklist_entry"
    df_cl["redcap_repeat_instance"] = df_cl.groupby("record_id").cumcount() + 1

    # Final column order
    all_cols = df_cl.columns.tolist()
    all_cols = [c for c in all_cols if c not in ("redcap_repeat_instrument", "redcap_repeat_instance")]
    all_cols += ["redcap_repeat_instrument", "redcap_repeat_instance"]
    df_cl = df_cl[all_cols]

    # Ensure 'time_entered' is datetime
    df_cl["time_entered"] = pd.to_datetime(df_cl["time_entered"], errors="coerce")

    # Group by record_id and compute max and min start_date
    submitted_max = df_cl.groupby("record_id")["time_entered"].max().dt.strftime("%m-%d-%Y")
    #submitted_min = df_cl.groupby("record_id")["time_entered"].min().dt.strftime("%m-%d-%Y")

    # Add empty submitted_ce columns to df_cl so they exist for reordering
    df_cl["submitted_ce"] = ""
    #df_cl["submitted_ce_min"] = ""
    df_cl["checklist_entry_complete"] = 2

    # Create summary rows (non-repeating)
    df_summary = pd.DataFrame({
        "record_id": submitted_max.index,
        "submitted_ce": submitted_max.values,
        #"submitted_ce_min": submitted_min.values,
        "redcap_repeat_instrument": "",
        "redcap_repeat_instance": "",
        "checklist_entry_complete": "",
    })

    # Add missing columns to match df_cl
    for col in df_cl.columns:
        if col not in df_summary.columns:
            df_summary[col] = ""

    # Align column order
    df_summary = df_summary[df_cl.columns]

    # Concatenate checklist entries + summary rows
    df_cl = pd.concat([df_cl, df_summary], ignore_index=True)

    # Move key columns to front
    #front_cols = ["record_id", "submitted_ce", "submitted_ce_min"]
    front_cols = ["record_id", "submitted_ce"]
    rest_cols = [c for c in df_cl.columns if c not in front_cols]
    df_cl = df_cl[front_cols + rest_cols]

    # Now drop unnecessary columns
    df_cl = df_cl.drop(columns=["email", "date", "start_date"])

    # Show + download
    st.dataframe(df_cl, height=400)
    st.download_button(
        "📥 Download formatted checklist CSV",
        df_cl.to_csv(index=False).encode("utf-8"),
        file_name="checklist_entries.csv",
        mime="text/csv",
    )


# ─── NBME Score ─────────────────────────────────────────────────────────────

