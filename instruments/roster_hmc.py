# Roster_HMC
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
    st.header("🔖 Roster_HMC")
    st.markdown("[🔗 Roster Website](https://oasis.pennstatehealth.net/admin/course/roster/)")

    # upload exactly one CSV
    roster_file = st.file_uploader("Upload exactly one Roster CSV",type=["csv"],accept_multiple_files=False,key="roster")
    
    if not roster_file:
        st.stop()

    # read as CSV
    df_roster = pd.read_csv(roster_file, dtype=str)

    df_roster.columns = df_roster.columns.str.strip()

    # map your columns to REDCap-friendly names
    rename_map = {
        "#":                              "row_number",
        "Student":                        "student",
        "Legal Name":                     "legal_name",
        "Previous Name":                  "previous_name",
        "Username":                       "username",
        "Confidential":                   "confidential",
        "External ID":                    "record_id",
        "Email Address":                  "email",
        "Phone":                          "phone",
        "Pager":                          "pager",
        "Mobile":                         "mobile",
        "Gender":                         "gender",
        "Pronouns":                       "pronouns",
        "Ethnicity":                      "ethnicity",
        "Designation":                    "designation",
        "AAMC ID":                        "aamc_id",
        "USMLE ID":                       "usmle_id",
        "Home School":                    "home_school",
        "Campus":                         "campus",
        "Date of Birth":                  "date_of_birth",
        "Emergency Contact":              "emergency_contact",
        "Emergency Phone":                "emergency_phone",
        "Primary Academic Department":    "primary_academic_department",
        "Secondary Academic Department":  "secondary_academic_department",
        "Academic Type":                  "academic_type",
        "Primary Site":                   "primary_site",
        "NBME":                           "nbme_score",
        "PSU ID":                         "psu_id",
        "Productivity Specialty":         "productivity_specialty",
        "Grade":                          "grade",
        "Status":                         "status",
        "Student Level":                  "student_level",
        "Track":                          "track",
        "Location":                       "location",
        "Start Date":                     "start_date",
        "End Date":                       "end_date",
        "Weeks":                          "weeks",
        "Credits":                        "credits",
        "Enrolled":                       "enrolled",
        "Actions":                        "actions",
        "Aprv By":                     "approved_by"
    }
    df_roster = df_roster.rename(columns=rename_map)

    # keep only those renamed columns (in this exact order)
    df_roster = df_roster[list(rename_map.values())]

    # move record_id to the front
    cols = ["record_id"] + [c for c in df_roster.columns if c != "record_id"]
    df_roster = df_roster[cols]

    # add REDCap repeater - dont need
    #df_roster["redcap_repeat_instrument"] = "roster"
    #df_roster["redcap_repeat_instance"]   = df_roster.groupby("record_id").cumcount() + 1

    # ─── split “student” into last_name / first_name ─────────────────────────
    # 1) drop everything after the semicolon
    name_only = df_roster["student"].str.split(";", n=1).str[0]
    # 2) split on comma into last / first
    parts = name_only.str.split(",", n=1, expand=True)
    df_roster["lastname"]  = parts[0].str.strip()
    df_roster["firstname"] = parts[1].str.strip()

    df_roster["name"] = df_roster["firstname"] + " " + df_roster["lastname"]

    df_roster["legal_name"] = df_roster["lastname"] + ", " + df_roster["firstname"] + " (MD)" 

    df_roster["email_2"] = df_roster["record_id"] + "@psu.edu"

    #legal name ... legal_name
    
    # 3) (optional) drop the original combined column
    renamed_cols_a = ["row_number","student","previous_name","username","confidential","phone","pager","mobile","gender","pronouns","ethnicity","designation","aamc_id","usmle_id","home_school"]
    renamed_cols_b = ["campus","date_of_birth","emergency_contact","emergency_phone","primary_academic_department","secondary_academic_department","academic_type","primary_site","nbme_score"]
    renamed_cols_c = ["productivity_specialty","grade","status","student_level","weeks","credits","enrolled","actions","approved_by"]

    renamed_cols = renamed_cols_a + renamed_cols_b + renamed_cols_c
    
    # 0) ensure start_date is a true datetime
    df_roster["start_date"] = pd.to_datetime(df_roster["start_date"], errors='coerce')
    
    # 1) grab each unique date, sorted oldest → newest
    unique_dates = sorted(df_roster["start_date"].dropna().unique())
    
    # 2) for each one, make a new column rot_date_#
    for idx, dt in enumerate(unique_dates, 1):
        df_roster[f"rot_date_{idx}"] = df_roster["start_date"].apply(lambda x: dt.strftime("%m-%d-%Y") if pd.notna(x) and x == dt else "")

    # 3) build a mapping from date → rotation code
    rotation_map = {dt: f"r{idx:02}" for idx, dt in enumerate(unique_dates, 1)}
    
    # 4) assign each student’s rotation1 based on their start_date
    df_roster["rotation1"] = df_roster["start_date"].map(rotation_map)

    df_roster["rotation"] = df_roster["start_date"].map(rotation_map)

    # 3) now drop your old columns
    df_roster.drop(columns=renamed_cols, errors="ignore", inplace=True)

    #DUE DATES
    
    # ─── 1) Ensure start_date and end_date are datetime ─────────────────────────
    df_roster["start_date"] = pd.to_datetime(df_roster["start_date"], errors="coerce")
    df_roster["end_date"]   = pd.to_datetime(df_roster["end_date"], errors="coerce")
    
    # ─── 2) Compute first Sunday on/after start_date ────────────────────────────
    days_to_sunday = (6 - df_roster["start_date"].dt.weekday) % 7
    first_sunday   = df_roster["start_date"] + pd.to_timedelta(days_to_sunday, unit="D")
    
    # ─── 3) Create quiz_due_1 … quiz_due_4 ──────────────────────────────────────
    for n in range(1, 5):
        df_roster[f"quiz_due_{n}"] = first_sunday + pd.Timedelta(weeks=(n - 1))
    
    # ─── 4) Alias assignment & doc-assignment due dates ─────────────────────────
    #df_roster["ass_middue_date"]   = df_roster["quiz_due_2"]
    df_roster["ass_due_date"]      = df_roster["quiz_due_4"]
    #df_roster["docass_due_date_1"] = df_roster["quiz_due_2"]
    #df_roster["docass_due_date_2"] = df_roster["quiz_due_4"]
    
    # ─── 5) Grade due date: 6 weeks after end_date ──────────────────────────────
    df_roster["grade_due_date"] = df_roster["end_date"] + pd.Timedelta(weeks=6)
    df_roster["grade_due_date2"] = df_roster["end_date"] + pd.Timedelta(weeks=6)
    
    # ─── 6) Normalize all due dates to 23:59 with no seconds ─────────────────
    #due_cols = ["quiz_due_1","quiz_due_2","quiz_due_3","quiz_due_4","ass_middue_date","ass_due_date","docass_due_date_1","docass_due_date_2","grade_due_date"]
    
    due_cols = ["ass_due_date","grade_due_date"]
    
    for col in due_cols:
        df_roster[col] = (df_roster[col].dt.normalize() + pd.Timedelta(hours=23, minutes=59)).dt.strftime("%m-%d-%Y 23:59")

    df_roster["start_date"] = df_roster["start_date"].dt.strftime("%m-%d-%Y")
    df_roster["end_date"] = df_roster["end_date"].dt.strftime("%m-%d-%Y")
    df_roster["grade_due_date2"] = df_roster["grade_due_date2"].dt.strftime("%m-%d-%Y")
    
    df_roster["student_demographics_complete"] = 2 
    
    # --------- REMOVE QUIZ DUE COLUMNS COMPLETELY ----------
    df_roster = df_roster.drop(columns=[c for c in df_roster.columns if c.startswith("quiz_due_") or c.startswith("rot_date")],errors="ignore")

    st.dataframe(df_roster, height=400)

    st.download_button("📥 Download formatted Roster CSV",df_roster.to_csv(index=False).encode("utf-8"),file_name="roster_formatted.csv",mime="text/csv")

    # --------- BUILD ROTATION START DATE FILE ----------
    rotation_reference = pd.DataFrame({
        "rotation_code": [rotation_map[dt] for dt in unique_dates],
        "start_date": [pd.to_datetime(dt).strftime("%m-%d-%Y") for dt in unique_dates]
    })
    rotation_text = "\n".join(
    f"{row.rotation_code}, {row.start_date}"
    for _, row in rotation_reference.iterrows()
)

    st.download_button(
        "📥 Download Rotation Start Dates For RedCap(.txt)",
        rotation_text,
        file_name="rotation_start_dates.txt",
        mime="text/plain"
    )

    # --------- REMOVE QUIZ DUE COLUMNS COMPLETELY ----------
    df_roster = (df_roster[['record_id','lastname', 'firstname', 'email', 'rotation','student_demographics_complete']].rename(columns={'lastname': 'last_name','firstname': 'first_name','student_demographics_complete': 'pediatric_clerkship_intake_form_complete'}))
    
    st.download_button("📥 Download roster_intake_form csv",df_roster.to_csv(index=False).encode("utf-8"),file_name="roster_intake_form.csv",mime="text/csv")

