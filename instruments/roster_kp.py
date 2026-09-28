# Roster_KP
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
    st.header("🔖 Roster KPLIC")
    st.markdown("[🔗 Roster Website](https://oasis.pennstatehealth.net/admin/course/roster/)")

    roster_file = st.file_uploader(
        "Upload exactly one KPLIC Roster CSV",
        type=["csv"],
        accept_multiple_files=False,
        key="roster_kplic"
    )

    if not roster_file:
        st.stop()

    def clean_text(x):
        if pd.isna(x):
            return ""
        return str(x).strip()

    def safe_date(x):
        x = clean_text(x)
        if x == "":
            return pd.NaT
        return pd.to_datetime(x, errors="coerce")

    try:
        df_roster = pd.read_csv(roster_file, dtype=str).fillna("")
    except Exception as e:
        st.error(f"Could not read roster file: {e}")
        st.stop()

    df_roster.columns = df_roster.columns.str.strip()

    rename_map = {
        "Student": "student",
        "Legal Name": "legal_name",
        "External ID": "record_id",
        "Email Address": "email",
        "PSU ID": "psu_id",
        "Track": "track",
        "Location": "location",
        "Start Date": "start_date",
        "End Date": "end_date"
    }

    missing_cols = [col for col in rename_map if col not in df_roster.columns]

    if missing_cols:
        st.error(f"The uploaded OASIS file is missing these required columns: {missing_cols}")
        st.stop()

    df_roster = df_roster.rename(columns=rename_map)

    redcap_cols = [
        "record_id",
        "legal_name",
        "email",
        "psu_id",
        "track",
        "location",
        "start_date",
        "end_date",
        "lastname",
        "firstname",
        "name",
        "email_2",
        "rotation1",
        "rotation",
        "ass_due_date",
        "grade_due_date",
        "student_demographics_complete"
    ]

    for col in redcap_cols:
        if col not in df_roster.columns:
            df_roster[col] = ""

    df_roster["record_id"] = df_roster["record_id"].apply(clean_text).str.lower()
    df_roster["email"] = df_roster["email"].apply(clean_text)
    df_roster["psu_id"] = df_roster["psu_id"].apply(clean_text)
    df_roster["track"] = df_roster["track"].apply(clean_text)
    df_roster["location"] = df_roster["location"].apply(clean_text)

    blank_ids = df_roster[df_roster["record_id"] == ""].copy()

    if len(blank_ids) > 0:
        st.warning(f"{len(blank_ids)} rows had blank External ID and were removed.")
        st.dataframe(blank_ids)

    df_roster = df_roster[df_roster["record_id"] != ""].copy()

    dupes = df_roster[df_roster["record_id"].duplicated(keep=False)].copy()

    if len(dupes) > 0:
        st.warning("Duplicate record_ids found. Keeping the first occurrence.")
        st.dataframe(dupes)

    df_roster = df_roster.drop_duplicates(subset=["record_id"], keep="first")

    name_only = df_roster["student"].astype(str).str.split(";", n=1).str[0]
    parts = name_only.str.split(",", n=1, expand=True)

    df_roster["lastname"] = parts[0].fillna("").str.strip()
    df_roster["firstname"] = parts[1].fillna("").str.strip()

    df_roster["name"] = (df_roster["firstname"] + " " + df_roster["lastname"]).str.strip()
    df_roster["legal_name"] = (df_roster["lastname"] + ", " + df_roster["firstname"] + " (MD)").str.strip()
    df_roster["email_2"] = df_roster["record_id"] + "@psu.edu"

    df_roster["start_date"] = df_roster["start_date"].apply(safe_date)
    df_roster["end_date"] = df_roster["end_date"].apply(safe_date)

    bad_dates = df_roster[
        df_roster["start_date"].isna() | df_roster["end_date"].isna()
    ].copy()

    if len(bad_dates) > 0:
        st.warning(f"{len(bad_dates)} rows have invalid or missing start/end dates.")
        st.dataframe(bad_dates[["record_id", "legal_name", "start_date", "end_date"]])

    df_roster["rotation1"] = "KPLIC"
    df_roster["rotation"] = "KPLIC"

    days_to_sunday = (6 - df_roster["start_date"].dt.weekday) % 7
    first_sunday = df_roster["start_date"] + pd.to_timedelta(days_to_sunday, unit="D")

    df_roster["ass_due_date"] = first_sunday + pd.Timedelta(weeks=3)
    df_roster["grade_due_date"] = df_roster["end_date"] + pd.Timedelta(weeks=6)

    for col in ["ass_due_date", "grade_due_date"]:
        df_roster[col] = (
            df_roster[col]
            .dt.normalize()
            .add(pd.Timedelta(hours=23, minutes=59))
            .dt.strftime("%m-%d-%Y 23:59")
            .fillna("")
        )

    df_roster["start_date"] = df_roster["start_date"].dt.strftime("%m-%d-%Y").fillna("")
    df_roster["end_date"] = df_roster["end_date"].dt.strftime("%m-%d-%Y").fillna("")

    df_roster["student_demographics_complete"] = "2"

    df_roster = df_roster[redcap_cols].copy()

    st.subheader("Preview of KPLIC REDCap Roster")
    st.dataframe(df_roster, height=400)

    st.download_button(
        "📥 Download KPLIC REDCap Roster CSV",
        df_roster.to_csv(index=False).encode("utf-8-sig"),
        file_name="kplic_roster_formatted.csv",
        mime="text/csv"
    )

    df_intake = df_roster[
        ["record_id", "lastname", "firstname", "email", "rotation", "student_demographics_complete"]
    ].rename(
        columns={
            "lastname": "last_name",
            "firstname": "first_name",
            "student_demographics_complete": "pediatric_clerkship_intake_form_complete"
        }
    )

    st.download_button(
        "📥 Download KPLIC Intake Form CSV",
        df_intake.to_csv(index=False).encode("utf-8-sig"),
        file_name="kplic_roster_intake_form.csv",
        mime="text/csv"
    )
    
