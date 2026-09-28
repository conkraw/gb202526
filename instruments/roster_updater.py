# Roster_Updater
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
    st.header("🔖 Roster Updater")
    st.markdown("[🔗 Roster Website](https://oasis.pennstatehealth.net/admin/course/roster/)")

    import pandas as pd

    old_file = st.file_uploader(
        "Upload OLD REDCap Roster CSV",
        type=["csv"],
        accept_multiple_files=False,
        key="old_roster"
    )

    new_file = st.file_uploader(
        "Upload NEW OASIS Roster CSV",
        type=["csv"],
        accept_multiple_files=False,
        key="new_roster"
    )

    if not old_file or not new_file:
        st.stop()

    def clean_text(x):
        if pd.isna(x):
            return ""
        return str(x).strip()

    def format_date(x):
        x = clean_text(x)
        if x == "":
            return ""
        parsed = pd.to_datetime(x, errors="coerce")
        if pd.isna(parsed):
            return ""
        return parsed.strftime("%m-%d-%Y")

    def read_csv_safely(file, label):
        try:
            return pd.read_csv(file, dtype=str).fillna("")
        except Exception as e:
            st.error(f"Could not read {label} file: {e}")
            st.stop()

    df_old = read_csv_safely(old_file, "OLD REDCap")
    df_oasis = read_csv_safely(new_file, "NEW OASIS")

    redcap_cols = [
        "record_id", "legal_name", "email", "psu_id", "track", "location",
        "start_date", "end_date", "lastname", "firstname", "name", "email_2",
        "rotation1", "rotation", "ass_due_date", "grade_due_date",
        "student_demographics_complete"
    ]

    for col in redcap_cols:
        if col not in df_old.columns:
            df_old[col] = ""

    df_old = df_old[redcap_cols].copy()

    required_oasis_cols = {
        "External ID": "record_id",
        "Student": "legal_name",
        "Email Address": "email",
        "PSU ID": "psu_id",
        "Track": "track",
        "Location": "location",
        "Start Date": "start_date",
        "End Date": "end_date"
    }

    missing = [col for col in required_oasis_cols if col not in df_oasis.columns]

    if missing:
        st.error(f"The OASIS file is missing these required columns: {missing}")
        st.stop()

    df_new = pd.DataFrame()
    date_cols = ["start_date", "end_date"]

    for oasis_col, redcap_col in required_oasis_cols.items():
        if redcap_col in date_cols:
            df_new[redcap_col] = df_oasis[oasis_col].apply(format_date)
        else:
            df_new[redcap_col] = df_oasis[oasis_col].apply(clean_text)

    df_new["legal_name"] = (
        df_new["legal_name"]
        .str.replace("; MD2028", " (MD)", regex=False)
        .str.replace("; MD2027", " (MD)", regex=False)
        .str.replace("; MD2026", " (MD)", regex=False)
        .str.strip()
    )

    df_new["lastname"] = df_new["legal_name"].str.split(",", n=1).str[0].str.strip()

    df_new["firstname"] = (
        df_new["legal_name"]
        .str.split(",", n=1)
        .str[1]
        .fillna("")
        .str.replace("(MD)", "", regex=False)
        .str.strip()
    )

    df_new["name"] = (df_new["firstname"] + " " + df_new["lastname"]).str.strip()

    df_new["email_2"] = df_new["record_id"].str.lower() + "@psu.edu"
    df_new["rotation1"] = ""
    df_new["rotation"] = ""
    df_new["ass_due_date"] = ""
    df_new["grade_due_date"] = ""
    df_new["student_demographics_complete"] = "2"

    df_new = df_new[redcap_cols].copy()

    # Clean IDs
    df_old["record_id"] = df_old["record_id"].apply(clean_text).str.lower()
    df_new["record_id"] = df_new["record_id"].apply(clean_text).str.lower()

    # Ignore KPLIC from OLD REDCap only
    df_old["rotation"] = df_old["rotation"].astype(str).str.strip()

    old_kplic = df_old[
        df_old["rotation"].str.upper() == "KPLIC"
    ].copy()

    df_old = df_old[
        df_old["rotation"].str.upper() != "KPLIC"
    ].copy()

    if len(old_kplic) > 0:
        st.info(f"Ignored {len(old_kplic)} OLD REDCap rows where rotation = KPLIC.")
        st.dataframe(old_kplic[["record_id", "legal_name", "rotation"]])

    # Remove blank IDs
    blank_old_ids = df_old[df_old["record_id"] == ""].copy()
    blank_new_ids = df_new[df_new["record_id"] == ""].copy()

    if len(blank_old_ids) > 0:
        st.warning(f"{len(blank_old_ids)} rows in OLD REDCap file had blank record_id and were removed.")
        st.dataframe(blank_old_ids)

    if len(blank_new_ids) > 0:
        st.warning(f"{len(blank_new_ids)} rows in NEW OASIS file had blank External ID and were removed.")
        st.dataframe(blank_new_ids)

    df_old = df_old[df_old["record_id"] != ""].copy()
    df_new = df_new[df_new["record_id"] != ""].copy()

    # Duplicate protection
    old_dupes = df_old[df_old["record_id"].duplicated(keep=False)].copy()
    new_dupes = df_new[df_new["record_id"].duplicated(keep=False)].copy()

    if len(old_dupes) > 0:
        st.warning("Duplicate record_ids found in OLD REDCap file. Keeping the first occurrence.")
        st.dataframe(old_dupes)

    if len(new_dupes) > 0:
        st.warning("Duplicate record_ids found in NEW OASIS file. Keeping the first occurrence.")
        st.dataframe(new_dupes)

    df_old = df_old.drop_duplicates(subset=["record_id"], keep="first")
    df_new = df_new.drop_duplicates(subset=["record_id"], keep="first")

    # Format all date columns safely
    for col in ["start_date", "end_date", "ass_due_date", "grade_due_date"]:
        df_old[col] = df_old[col].apply(format_date)
        df_new[col] = df_new[col].apply(format_date)

    # Dropped students = OLD REDCap students not present in NEW OASIS
    new_ids = set(df_new["record_id"])
    df_dropped = df_old[~df_old["record_id"].isin(new_ids)].copy()

    # Clear rotation fields for dropped students
    df_dropped["rotation"] = ""
    df_dropped["rotation1"] = ""
    df_dropped["start_date"] = ""
    df_dropped["end_date"] = ""
    df_dropped["ass_due_date"] = ""
    df_dropped["grade_due_date"] = ""

    # Combine active/moved students from OASIS + dropped students from REDCap
    df_combined = pd.concat([df_new, df_dropped], ignore_index=True)
    df_combined = df_combined.drop_duplicates(subset=["record_id"], keep="first")

    # Final date check
    invalid_dates = []

    for col in ["start_date", "end_date", "ass_due_date", "grade_due_date"]:
        bad_rows = df_combined[
            (df_combined[col] != "") &
            (~df_combined[col].str.match(r"^\d{2}-\d{2}-\d{4}$", na=False))
        ].copy()

        if len(bad_rows) > 0:
            bad_rows["date_column"] = col
            invalid_dates.append(bad_rows)

    st.subheader("Summary")
    st.write(f"Rows in OLD REDCap file after removing KPLIC and blank IDs: {len(df_old)}")
    st.write(f"Rows in NEW OASIS file after removing blank IDs: {len(df_new)}")
    st.write(f"Dropped students retained with rotation cleared: {len(df_dropped)}")
    st.write(f"Final unique records: {len(df_combined)}")

    if len(invalid_dates) > 0:
        st.warning("Some dates may not be formatted correctly.")
        st.dataframe(pd.concat(invalid_dates, ignore_index=True))
    else:
        st.success("All dates are formatted as MM-DD-YYYY.")

    st.subheader("Dropped Students")

    if len(df_dropped) > 0:
        st.dataframe(
            df_dropped[
                ["record_id", "legal_name", "rotation", "rotation1", "start_date", "end_date"]
            ]
        )
    else:
        st.success("No dropped students found.")

    st.subheader("Preview of Updated Roster")
    st.dataframe(df_combined)

    csv_output = df_combined.to_csv(index=False).encode("utf-8-sig")

    st.download_button(
        label="Download Updated REDCap Roster CSV",
        data=csv_output,
        file_name="updated_roster.csv",
        mime="text/csv"
    )

    dropped_output = df_dropped.to_csv(index=False).encode("utf-8-sig")

    st.download_button(
        label="Download Dropped Students CSV",
        data=dropped_output,
        file_name="dropped_students.csv",
        mime="text/csv"
    )
