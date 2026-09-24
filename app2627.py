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


st.set_page_config(page_title="REDCap Formatter", layout="wide")
st.title("🔄 REDCap Instruments Formatter")
st.markdown("[Open REDCap Data Import](https://redcap.ctsi.psu.edu/redcap_v15.5.35/index.php?pid=19389&route=DataImportController:index)")


# choose which instrument you want to format
instrument = st.sidebar.selectbox("Select instrument", ["OASIS Evaluation", "Checklist Entry", "Preceptor Matching", "NBME Scores", "Roster_HMC", "Roster_KP", "Roster_Updater","Oasis Reminder","Session Feedback Link Creator","Session Feedback Summary Creator"])

if instrument == "OASIS Evaluation":
    st.header("📋 OASIS Evaluation Formatter")
    st.markdown("[Open OASIS Clinical Assessment of Student Setup](https://oasis.pennstatehealth.net/admin/course/e_manage/student_performance/setup_analysis_report.html)")

    uploaded = st.file_uploader("Upload your raw OASIS CSV", type="csv", key="oasis")
    if not uploaded:
        st.stop()

    df = pd.read_csv(uploaded, dtype=str)

    # 自动把 "Course ID"→"course_id", "1 Question Number"→"q1_question_number", …
    def rename_oasis(col: str) -> str:
        col = col.strip()
        m = re.match(r"^(\d+)\s+(.+)$", col)
        if m:
            num, rest = m.groups()
            return f"q{num}_{rest.lower().replace(' ', '_')}"
        return col.lower().replace(" ", "_")

    df.columns = [rename_oasis(c) for c in df.columns]

    # build master_cols
    front = [
        "record_id","course_id","department","course","location",
        "start_date","end_date","course_type","student","student_username",
        "student_external_id","student_designation","student_email",
        "student_aamc_id","student_usmle_id","student_gender","student_level",
        "student_default_classification","evaluator","evaluator_username",
        "evaluator_external_id","evaluator_email","evaluator_gender",
        "who_completed","evaluation","form_record","submit_date"
    ]
    q_sufs = [
        "question_number","question_id","question","answer_text",
        "multiple_choice_order","multiple_choice_value","multiple_choice_label"
    ]
    questions = [f"q{i}_{s}" for i in range(1,24) for s in q_sufs]
    tail = ["oasis_eval_complete"]
    master_cols = front + questions + tail

    # reorder (will KeyError if you missed any)
    df = df.reindex(columns=master_cols)

    # inject REDCap fields
    df["record_id"]                = df["student_external_id"]
    df["redcap_repeat_instrument"] = "oasis_eval"
    df["redcap_repeat_instance"]   = df.groupby("record_id").cumcount() + 1

    # final column order
    keep_front = ["record_id","redcap_repeat_instrument","redcap_repeat_instance"]
    rest       = [c for c in master_cols if c not in keep_front]
    df = df.reindex(columns=keep_front + rest)


    # 8) remove student & location
    df = df.drop(columns=["student","location","start_date","end_date","location"]) #Cannot have these columns in the repeating instrument. 

    df["oasis_eval_complete"] = 2 
    
    st.dataframe(df, height=400)
    st.download_button(
        "📥 Download formatted OASIS CSV",
        df.to_csv(index=False).encode("utf-8"),
        file_name="oasis_eval_formatted.csv",
        mime="text/csv",
    )

elif instrument == "Checklist Entry":
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

elif instrument == "NBME Scores":
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

elif instrument == "Preceptor Matching":
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
    


elif instrument == "Roster_HMC":
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

elif instrument == "Roster_KP":
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
    
elif instrument == "Roster_Updater":
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
elif instrument == "Oasis Reminder":
    # ============================================================
    # Evaluation configuration
    # ============================================================
    @dataclass(frozen=True)
    class EvalConfig:
        label: str                    # sidebar/display label
        match_name: str               # raw OASIS / association form name after cleaning
        output_name: str              # value written to output CSV
        redcap_base_url: str          # prefilled survey URL base
        note_style: str               # "cas" or "hp" or "generic"
    
    
    EVAL_CONFIGS: list[EvalConfig] = [
        EvalConfig(
            label="Clinical Assessment of Student",
            match_name="Clinical Assessment of Student",
            output_name="Clinical Assessment of Student",
            redcap_base_url="https://redcap.ctsi.psu.edu/surveys/?s=C7EJ3MPDMCMCFJEP",
            note_style="cas",
        ),
        EvalConfig(
            label="Observed H&P / PEDS History Taking & Physical Exam",
            match_name="PEDS History Taking & Physical Exam",
            output_name="PEDS History Taking & Physical Exam",
            redcap_base_url="https://redcap.ctsi.psu.edu/surveys/?s=8C7DLPNX8LT9HTJP",
            note_style="hp",
        ),
    ]
    
    
    # ============================================================
    # General helpers
    # ============================================================
    def read_csv_any(uploaded_file) -> pd.DataFrame:
        """Read a user-uploaded CSV with a few encoding fallbacks."""
        if uploaded_file is None:
            return pd.DataFrame()
    
        raw = uploaded_file.getvalue()
        last_error = None
    
        for enc in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                return pd.read_csv(BytesIO(raw), dtype=str, encoding=enc).fillna("")
            except Exception as e:  # pragma: no cover - displayed in Streamlit
                last_error = e
    
        raise ValueError(f"Could not read CSV. Last error: {last_error}")
    
    
    def normalize_colnames(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df.columns = [str(c).strip().lstrip("\ufeff") for c in df.columns]
        return df
    
    
    def first_existing_col(df: pd.DataFrame, candidates: Iterable[str]) -> str | None:
        for c in candidates:
            if c in df.columns:
                return c
        return None
    
    
    def clean_text(x) -> str:
        return re.sub(r"\s+", " ", str(x or "").strip())
    
    
    def clean_eval_name(x) -> str:
        """Normalize evaluation names from both files: remove leading asterisks, normalize spacing/case."""
        s = clean_text(x)
        s = s.lstrip("*").strip()
        return re.sub(r"\s+", " ", s).lower()
    
    
    def display_eval_name(x) -> str:
        """Human-facing evaluation name."""
        s = clean_text(x).lstrip("*").strip()
        return re.sub(r"\s+", " ", s)
    
    
    def clean_email(x) -> str:
        return clean_text(x).lower()
    
    
    def clean_id(x) -> str:
        return clean_text(x).lower()
    
    
    def clean_name_for_display(x) -> str:
        """
        Convert 'Last, First; MD2028' or 'Last - First' to 'First Last'.
        Leaves already-readable names alone.
        """
        s = clean_text(x)
        s = re.sub(r";\s*MD\d{4}", "", s, flags=re.IGNORECASE).strip()
    
        if " - " in s:
            last, first = s.split(" - ", 1)
            return f"{first.strip()} {last.strip()}".strip()
    
        if "," in s:
            last, first = s.split(",", 1)
            return f"{first.strip()} {last.strip()}".strip()
    
        return s
    
    
    def to_date(s: pd.Series) -> pd.Series:
        return pd.to_datetime(s, errors="coerce").dt.normalize()
    
    
    def make_prefill_link(base_url: str, student_name: str, faculty_name: str, partial: bool = False) -> str:
        if not base_url:
            return ""
    
        url = (
            f"{base_url}"
            f"&student={quote_plus(str(student_name).strip())}"
            f"&preceptor={quote_plus(str(faculty_name).strip())}"
        )
    
        if partial:
            # Existing shortcut values from your prior scripts. Edit/remove if you ever change the REDCap forms.
            url += "&complete=1&ph=3&ch=3&pp=3&cp=3"
    
        return url
    
    
    def safe_for_power_automate(value) -> str:
        """
        Keep CSV simple for Flow/Power Automate:
        - no embedded line breaks
        - replace commas with hyphens, matching your prior scripts
        - no double quotes
        """
        s = str(value or "")
        s = s.replace(",", " -")
        s = s.replace('"', "")
        s = s.replace("\r", " ").replace("\n", " ")
        return re.sub(r"\s+", " ", s).strip()
    
    
    def config_maps(configs: list[EvalConfig]) -> tuple[dict[str, EvalConfig], dict[str, str]]:
        """Return maps keyed by normalized raw match names and sidebar labels."""
        by_key = {clean_eval_name(c.match_name): c for c in configs}
        label_to_key = {c.label: clean_eval_name(c.match_name) for c in configs}
        return by_key, label_to_key
    
    
    # ============================================================
    # Data preparation
    # ============================================================
    def prepare_expected_associations(
        assoc_raw: pd.DataFrame,
        selected_eval_keys: set[str],
        eval_config_by_key: dict[str, EvalConfig],
        as_of_date: pd.Timestamp,
        date_mode: str,
        include_all_students: bool,
    ) -> pd.DataFrame:
        """
        Convert raw evaluation_associations / preceptor matching file to one expected-evaluation row
        per student/faculty/evaluation association.
        """
        df = normalize_colnames(assoc_raw)
    
        # Support raw OASIS association headers and common REDCap-style lowercase headers.
        rename_variants = {
            "faculty_name": "Faculty Name",
            "faculty_username": "Faculty Username",
            "faculty_external_id": "Faculty External ID",
            "faculty_email": "Faculty Email",
            "student_name": "Student Name",
            "student_username": "Student Username",
            "record_id": "Student External ID",
            "student_email": "Student Email",
            "manual_evaluations": "Manual Evaluations",
            "start_date": "Start Date",
            "end_date": "End Date",
            "eval_period_start_date": "Evaluation Period Start Date",
            "eval_period_end_date": "Evaluation Period End Date",
        }
        present = {old: new for old, new in rename_variants.items() if old in df.columns and new not in df.columns}
        if present:
            df = df.rename(columns=present)
    
        required = [
            "Faculty Name",
            "Faculty Username",
            "Faculty External ID",
            "Faculty Email",
            "Student Name",
            "Student Username",
            "Student External ID",
            "Student Email",
            "Manual Evaluations",
        ]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"Association file is missing expected column(s): {missing}")
    
        # Prefer evaluation-period dates; fall back to course dates.
        eval_start_col = first_existing_col(df, ["Evaluation Period Start Date", "eval_period_start_date"])
        eval_end_col = first_existing_col(df, ["Evaluation Period End Date", "eval_period_end_date"])
        course_start_col = first_existing_col(df, ["Start Date", "start_date"])
        course_end_col = first_existing_col(df, ["End Date", "end_date"])
    
        df["expected_start_date"] = df[eval_start_col] if eval_start_col else ""
        df["expected_end_date"] = df[eval_end_col] if eval_end_col else ""
    
        if course_start_col:
            df["expected_start_date"] = df["expected_start_date"].replace("", pd.NA).fillna(df[course_start_col])
        if course_end_col:
            df["expected_end_date"] = df["expected_end_date"].replace("", pd.NA).fillna(df[course_end_col])
    
        # Remove all-student/global rows by default.
        if not include_all_students:
            df = df[
                ~df["Student External ID"].astype(str).str.strip().str.lower().eq("all students")
            ].copy()
    
        # Remove rows marked for deletion if present.
        if "Delete" in df.columns:
            df = df[df["Delete"].astype(str).str.strip().eq("")].copy()
    
        # Explode manual evaluations separated by pipes.
        df["manual_eval_item"] = df["Manual Evaluations"].astype(str).str.split("|")
        df = df.explode("manual_eval_item").copy()
        df["evaluation_key"] = df["manual_eval_item"].apply(clean_eval_name)
    
        # Drop blanks and keep selected tracked evaluations only.
        df = df[df["evaluation_key"].ne("")].copy()
        df = df[df["evaluation_key"].isin(selected_eval_keys)].copy()
    
        df["evaluation_type"] = df["evaluation_key"].map(
            lambda k: eval_config_by_key.get(k).output_name if k in eval_config_by_key else display_eval_name(k)
        )
        df["evaluation_label"] = df["evaluation_key"].map(
            lambda k: eval_config_by_key.get(k).label if k in eval_config_by_key else display_eval_name(k)
        )
    
        # Standard keys.
        df["record_id"] = df["Student External ID"].apply(clean_id)
        df["student_username_key"] = df["Student Username"].apply(clean_id)
        df["student_name"] = df["Student Name"].apply(clean_name_for_display)
        df["student_email"] = df["Student Email"].apply(clean_email)
    
        df["faculty_name"] = df["Faculty Name"].apply(clean_name_for_display)
        df["faculty_username_key"] = df["Faculty Username"].apply(clean_id)
        df["faculty_external_id_key"] = df["Faculty External ID"].apply(clean_id)
        df["faculty_email"] = df["Faculty Email"].apply(clean_email)
    
        df["expected_start"] = to_date(df["expected_start_date"])
        df["expected_end"] = to_date(df["expected_end_date"])
    
        # Date filter for reminders.
        if date_mode == "Active as of selected date":
            df = df[
                (df["expected_start"].notna())
                & (df["expected_end"].notna())
                & (df["expected_start"] <= as_of_date)
                & (df["expected_end"] >= as_of_date)
            ].copy()
        elif date_mode == "Evaluation period ended on/before selected date":
            df = df[
                (df["expected_end"].notna())
                & (df["expected_end"] <= as_of_date)
            ].copy()
        elif date_mode == "No date filter":
            pass
        else:
            raise ValueError(f"Unknown date_mode: {date_mode}")
    
        keep = [
            "record_id",
            "student_username_key",
            "student_name",
            "student_email",
            "faculty_name",
            "faculty_username_key",
            "faculty_external_id_key",
            "faculty_email",
            "evaluation_key",
            "evaluation_type",
            "evaluation_label",
            "expected_start",
            "expected_end",
        ]
        return df[keep].drop_duplicates().reset_index(drop=True)
    
    
    def prepare_completed_oasis(
        oasis_raw: pd.DataFrame,
        selected_eval_keys: set[str],
        eval_config_by_key: dict[str, EvalConfig],
    ) -> pd.DataFrame:
        """
        Convert raw OASIS question-level export to one row per submitted evaluation.
        """
        df = normalize_colnames(oasis_raw)
    
        # Normalize common OASIS column variants.
        rename_variants = {
            "Answer text": "Answer Text",
            "answer text": "Answer Text",
            "Multiple Choice Value": "Mult Choice Value",
            "Multiple choice value": "Mult Choice Value",
            "Student external id": "Student External ID",
            "Evaluator external id": "Evaluator External ID",
            "Submit date": "Submit Date",
            "Evaluator email": "Evaluator Email",
            "Student email": "Student Email",
        }
        present = {old: new for old, new in rename_variants.items() if old in df.columns and new not in df.columns}
        if present:
            df = df.rename(columns=present)
    
        required = [
            "Student",
            "Student Username",
            "Student External ID",
            "Student Email",
            "Evaluator",
            "Evaluator Username",
            "Evaluator External ID",
            "Evaluator Email",
            "Evaluation",
            "Submit Date",
        ]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"OASIS export is missing expected column(s): {missing}")
    
        start_col = first_existing_col(df, ["Start Date", "Evaluation Start Date"])
        end_col = first_existing_col(df, ["End Date", "Evaluation End Date"])
    
        df["evaluation_key"] = df["Evaluation"].apply(clean_eval_name)
        df = df[df["evaluation_key"].isin(selected_eval_keys)].copy()
    
        df["evaluation_type"] = df["evaluation_key"].map(
            lambda k: eval_config_by_key.get(k).output_name if k in eval_config_by_key else display_eval_name(k)
        )
        df["evaluation_label"] = df["evaluation_key"].map(
            lambda k: eval_config_by_key.get(k).label if k in eval_config_by_key else display_eval_name(k)
        )
    
        df["submit_dt"] = pd.to_datetime(df["Submit Date"], errors="coerce")
        df = df[df["submit_dt"].notna()].copy()
    
        df["record_id"] = df["Student External ID"].apply(clean_id)
        df["student_username_key"] = df["Student Username"].apply(clean_id)
        df["student_name"] = df["Student"].apply(clean_name_for_display)
        df["student_email"] = df["Student Email"].apply(clean_email)
    
        df["faculty_name"] = df["Evaluator"].apply(clean_name_for_display)
        df["faculty_username_key"] = df["Evaluator Username"].apply(clean_id)
        df["faculty_external_id_key"] = df["Evaluator External ID"].apply(clean_id)
        df["faculty_email"] = df["Evaluator Email"].apply(clean_email)
    
        df["oasis_start"] = to_date(df[start_col]) if start_col else pd.NaT
        df["oasis_end"] = to_date(df[end_col]) if end_col else pd.NaT
    
        # OASIS is usually question-level. Form Record is best if present.
        # Include evaluation_key in case Form Record is ever reused unexpectedly.
        if "Form Record" in df.columns:
            dedupe_cols = ["Form Record", "evaluation_key"]
        else:
            dedupe_cols = [
                "record_id",
                "student_username_key",
                "faculty_username_key",
                "faculty_external_id_key",
                "faculty_email",
                "evaluation_key",
                "submit_dt",
            ]
    
        keep = [
            "record_id",
            "student_username_key",
            "student_name",
            "student_email",
            "faculty_name",
            "faculty_username_key",
            "faculty_external_id_key",
            "faculty_email",
            "evaluation_key",
            "evaluation_type",
            "evaluation_label",
            "submit_dt",
            "oasis_start",
            "oasis_end",
        ]
        return df.drop_duplicates(subset=dedupe_cols)[keep].reset_index(drop=True)
    
    
    # ============================================================
    # Matching logic
    # ============================================================
    def row_matches(
        expected_row: pd.Series,
        completed: pd.DataFrame,
        allow_email_fallback: bool,
        allow_username_fallback: bool,
    ) -> pd.DataFrame:
        """
        Match expected association to completed OASIS submission.
    
        Important design choice:
        - Do not require date equality. Raw associations may use evaluation-period dates,
          while raw OASIS exports often use course dates.
        - Primary match: student external ID + evaluator external ID + evaluation.
        - Fallbacks: evaluator email and/or evaluator username when external ID is blank.
        """
        c = completed[completed["evaluation_key"].eq(expected_row["evaluation_key"])].copy()
    
        # Student match: external ID first. If external ID is missing, fall back to username.
        expected_record_id = expected_row.get("record_id", "")
        expected_student_username = expected_row.get("student_username_key", "")
    
        if expected_record_id:
            c = c[c["record_id"].eq(expected_record_id)].copy()
        elif expected_student_username:
            c = c[c["student_username_key"].eq(expected_student_username)].copy()
        else:
            return c.iloc[0:0].copy()
    
        if c.empty:
            return c
    
        # Evaluator match priority.
        expected_ext = expected_row.get("faculty_external_id_key", "")
        expected_email = expected_row.get("faculty_email", "")
        expected_username = expected_row.get("faculty_username_key", "")
    
        masks = []
    
        if expected_ext:
            masks.append(c["faculty_external_id_key"].eq(expected_ext))
    
        if allow_email_fallback and expected_email:
            masks.append(c["faculty_email"].eq(expected_email))
    
        if allow_username_fallback and expected_username:
            masks.append(c["faculty_username_key"].eq(expected_username))
    
        if not masks:
            return c.iloc[0:0].copy()
    
        combined_mask = masks[0]
        for m in masks[1:]:
            combined_mask = combined_mask | m
    
        return c[combined_mask].copy()
    
    
    def build_reminder_note(note_style: str, expected: int, completed: int) -> str:
        pending = max(expected - completed, 0)
        if pending <= 0:
            return ""
    
        if note_style == "hp":
            if expected == 1 and completed == 0:
                return "The student indicated that you observed an H&P encounter with them, but we have not yet received the corresponding formative assessment."
            if expected > 1 and completed == 0:
                return f"The student indicated that you observed {expected} H&P encounters with them, but we have not yet received any formative assessments."
            return f"The student indicated that you observed {expected} H&P encounters with them. We have received {completed} submission(s) so far and are still missing {pending}."
    
        if note_style == "cas":
            if expected == 1 and completed == 0:
                return "The student reported working with you, but we have not yet received the corresponding evaluation."
            if expected > 1 and completed == 0:
                return f"The student reported working with you on {expected} occasions, but we have not yet received any completed evaluations."
            return f"The student reported working with you on {expected} occasions. We have received {completed} completed evaluation(s) so far and are still missing {pending}."
    
        # Generic fallback.
        if expected == 1 and completed == 0:
            return "The student reported working with you, but we have not yet received the corresponding evaluation."
        return f"The student reported {expected} expected evaluation(s). We have received {completed} submission(s) and are still missing {pending}."
    
    
    def build_reminder_report(
        expected: pd.DataFrame,
        completed: pd.DataFrame,
        allow_email_fallback: bool,
        allow_username_fallback: bool,
        eval_config_by_key: dict[str, EvalConfig],
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Return:
          reminders: Power Automate-ready pending rows across all selected evaluation types
          debug: all expected rows with matched count/status
        """
        rows = []
    
        for _, e in expected.iterrows():
            matches = row_matches(e, completed, allow_email_fallback, allow_username_fallback)
            completed_count = len(matches)
    
            row = e.to_dict()
            row["completed_eval_count"] = completed_count
            row["completed_submit_dates"] = "; ".join(
                matches["submit_dt"].dt.strftime("%Y-%m-%d %H:%M:%S").dropna().unique().tolist()
            )
            row["matched_faculty_names"] = "; ".join(
                sorted(set(x for x in matches["faculty_name"].astype(str).tolist() if x.strip()))
            )
            rows.append(row)
    
        debug_rows = pd.DataFrame(rows)
        if debug_rows.empty:
            return pd.DataFrame(), debug_rows
    
        # Collapse duplicated expected associations for the same student/faculty/eval.
        group_cols = [
            "record_id",
            "student_email",
            "student_name",
            "faculty_email",
            "faculty_name",
            "evaluation_key",
            "evaluation_type",
            "evaluation_label",
        ]
    
        collapsed = (
            debug_rows.groupby(group_cols, dropna=False)
            .agg(
                expected_eval_count=("evaluation_key", "size"),
                completed_eval_count=("completed_eval_count", "max"),
                first_expected_start=("expected_start", "min"),
                last_expected_end=("expected_end", "max"),
                completed_submit_dates=(
                    "completed_submit_dates",
                    lambda s: "; ".join(sorted(set("; ".join(s).split("; ")) - {""})),
                ),
                matched_faculty_names=(
                    "matched_faculty_names",
                    lambda s: "; ".join(sorted(set("; ".join(s).split("; ")) - {""})),
                ),
            )
            .reset_index()
        )
        collapsed.insert(collapsed.columns.get_loc("record_id") + 1, "student_last_name_debug", collapsed["student_name"].astype(str).str.split().str[-1])
        collapsed["pending_eval_count"] = (
            collapsed["expected_eval_count"] - collapsed["completed_eval_count"]
        ).clip(lower=0)
    
        collapsed["duplicate_match_flag"] = collapsed["expected_eval_count"].apply(lambda n: "YES" if n > 1 else "")
        collapsed["needs_reminder"] = collapsed["pending_eval_count"].apply(lambda n: "YES" if n > 0 else "")
    
        def note_for_row(r: pd.Series) -> str:
            config = eval_config_by_key.get(r["evaluation_key"])
            note_style = config.note_style if config else "generic"
            return build_reminder_note(
                note_style=note_style,
                expected=int(r["expected_eval_count"]),
                completed=int(r["completed_eval_count"]),
            )
    
        collapsed["reminder_note"] = collapsed.apply(note_for_row, axis=1)
    
        def base_for_row(r: pd.Series) -> str:
            config = eval_config_by_key.get(r["evaluation_key"])
            return config.redcap_base_url if config else ""
    
        collapsed["blank_form_link"] = collapsed.apply(
            lambda r: make_prefill_link(base_for_row(r), r["student_name"], r["faculty_name"], partial=False),
            axis=1,
        )
        collapsed["partial_form_link"] = collapsed.apply(
            lambda r: make_prefill_link(base_for_row(r), r["student_name"], r["faculty_name"], partial=True),
            axis=1,
        )
    
        reminders = collapsed[collapsed["needs_reminder"].eq("YES")].copy()
    
        final_cols = [
            "faculty_email",
            "faculty_name",
            "student_name",
            "student_email",
            "evaluation_type",
            "evaluation_label",
            "expected_eval_count",
            "completed_eval_count",
            "pending_eval_count",
            "duplicate_match_flag",
            "reminder_note",
            "blank_form_link",
            "partial_form_link",
            "record_id",
            "first_expected_start",
            "last_expected_end",
        ]
    
        reminders = reminders[final_cols].copy()
    
        for col in reminders.columns:
            reminders[col] = reminders[col].apply(safe_for_power_automate)
    
        return reminders.reset_index(drop=True), collapsed.reset_index(drop=True)
    
    
    # ============================================================
    # Streamlit UI
    # ============================================================
    st.set_page_config(
        page_title="OASIS Preceptor Reminder Builder",
        page_icon="📋",
        layout="wide",
    )
    
    st.title("📋 OASIS Preceptor Evaluation Reminder Builder")
    st.caption("VERSION: v2 — tracks Clinical Assessment of Student AND Observed H&P / PEDS History Taking & Physical Exam")
    st.write(
        "Upload the raw OASIS evaluation export and the raw evaluation associations/preceptor matching file. "
        "The app cross-references expected evaluations against submitted evaluations and generates a "
        "Power Automate-ready reminder CSV."
    )
    
    EVAL_CONFIG_BY_KEY, LABEL_TO_KEY = config_maps(EVAL_CONFIGS)
    DEFAULT_LABELS = [c.label for c in EVAL_CONFIGS]
    
    with st.sidebar:
        #st.success("✅ MULTI-FORM v2 LOADED")
        #st.caption("You should see checkboxes/multiselect for CAS and Observed H&P below. If not, you are running an old file.")
        st.header("Files")
        assoc_file = st.file_uploader(
            "Raw preceptor matching / evaluation associations CSV",
            type=["csv"],
            key="assoc_file",
        )
        oasis_file = st.file_uploader(
            "Raw OASIS evaluation submission export CSV",
            type=["csv"],
            key="oasis_file",
        )
    
        st.header("Evaluation types to track")
        selected_labels = st.multiselect(
            "Select one or more evaluations",
            options=DEFAULT_LABELS,
            default=DEFAULT_LABELS,
        )
    
        with st.expander("Optional: add a custom evaluation type"):
            custom_eval_name = st.text_input("Custom raw OASIS/association evaluation name", value="")
            custom_output_name = st.text_input("Custom output name", value="")
            custom_redcap_url = st.text_input("Custom REDCap survey base URL", value="")
    
        st.header("Date/settings")
        as_of_date = pd.to_datetime(
            st.date_input("As-of date", value=pd.Timestamp.today().date())
        ).normalize()
    
        date_mode = st.selectbox(
            "Which associations should be considered?",
            ["No date filter","Active as of selected date","Evaluation period ended on/before selected date",
            ],
            index=0,
        )
    
        include_all_students = st.checkbox("Include 'All Students' rows", value=False)
        allow_email_fallback = st.checkbox("Allow evaluator email fallback", value=True)
        allow_username_fallback = st.checkbox("Allow evaluator username fallback", value=True)
    
    # Build final config map including optional custom evaluation.
    selected_eval_keys = {LABEL_TO_KEY[label] for label in selected_labels}
    if custom_eval_name.strip():
        custom_config = EvalConfig(
            label=custom_output_name.strip() or custom_eval_name.strip(),
            match_name=custom_eval_name.strip(),
            output_name=custom_output_name.strip() or display_eval_name(custom_eval_name),
            redcap_base_url=custom_redcap_url.strip(),
            note_style="generic",
        )
        custom_key = clean_eval_name(custom_config.match_name)
        EVAL_CONFIG_BY_KEY = {**EVAL_CONFIG_BY_KEY, custom_key: custom_config}
        selected_eval_keys.add(custom_key)
    
    run_clicked = st.button("Build reminder CSV", type="primary")
    
    if not run_clicked:
        st.info("Upload both CSV files, confirm the evaluation types, then click **Build reminder CSV**.")
        st.stop()
    
    if assoc_file is None or oasis_file is None:
        st.error("Please upload both the raw association file and the raw OASIS evaluation export.")
        st.stop()
    
    if not selected_eval_keys:
        st.error("Please select at least one evaluation type to track.")
        st.stop()
    
    try:
        assoc_raw = read_csv_any(assoc_file)
        oasis_raw = read_csv_any(oasis_file)
    
        expected = prepare_expected_associations(
            assoc_raw=assoc_raw,
            selected_eval_keys=selected_eval_keys,
            eval_config_by_key=EVAL_CONFIG_BY_KEY,
            as_of_date=as_of_date,
            date_mode=date_mode,
            include_all_students=include_all_students,
        )
    
        completed = prepare_completed_oasis(
            oasis_raw=oasis_raw,
            selected_eval_keys=selected_eval_keys,
            eval_config_by_key=EVAL_CONFIG_BY_KEY,
        )
    
        reminders, debug = build_reminder_report(
            expected=expected,
            completed=completed,
            allow_email_fallback=allow_email_fallback,
            allow_username_fallback=allow_username_fallback,
            eval_config_by_key=EVAL_CONFIG_BY_KEY,
        )
    
    except Exception as e:  # pragma: no cover - shown in Streamlit
        st.exception(e)
        st.stop()
    
    # ============================================================
    # Results
    # ============================================================
    st.success("Done.")
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Evaluation types tracked", len(selected_eval_keys))
    m2.metric("Expected associations considered", len(expected))
    m3.metric("Submitted evaluations found", len(completed))
    m4.metric("Reminder rows", len(reminders))
    
    # Small counts by eval type.
    if not expected.empty:
        st.subheader("Counts by evaluation type")
        expected_counts = expected.groupby(["evaluation_type"], dropna=False).size().reset_index(name="expected_rows")
        completed_counts = completed.groupby(["evaluation_type"], dropna=False).size().reset_index(name="completed_rows")
        reminder_counts = reminders.groupby(["evaluation_type"], dropna=False).size().reset_index(name="reminder_rows") if not reminders.empty else pd.DataFrame(columns=["evaluation_type", "reminder_rows"])
        counts = expected_counts.merge(completed_counts, on="evaluation_type", how="outer").merge(reminder_counts, on="evaluation_type", how="outer").fillna(0)
        for c in ["expected_rows", "completed_rows", "reminder_rows"]:
            counts[c] = counts[c].astype(int)
        st.dataframe(counts, use_container_width=True)
    
    tab1, tab2, tab3, tab4 = st.tabs([
        "Combined Power Automate CSV",
        "Separate downloads",
        "Matched / debug view",
        "Raw normalized inputs",
    ])

    def sort_by_student_and_faculty_last_name(df):
        df = df.copy()
    
        df["_student_last_sort"] = (
            df["student_name"].astype(str).str.strip().str.split().str[-1].str.lower()
        )
    
        df["_faculty_last_sort"] = (
            df["faculty_name"].astype(str).str.strip().str.split().str[-1].str.lower()
        )
    
        df = df.sort_values(
            ["_student_last_sort", "_faculty_last_sort", "student_name", "faculty_name"],
            kind="stable"
        )
    
        return df.drop(columns=["_student_last_sort", "_faculty_last_sort"])
    
    with tab1:
        st.subheader("Power Automate-ready reminder files")
    
        reminders_sorted = reminders.copy()
    
        reminders_sorted["_student_last_sort"] = (
            reminders_sorted["student_name"].astype(str).str.strip().str.split().str[-1].str.lower()
        )
        reminders_sorted["_faculty_last_sort"] = (
            reminders_sorted["faculty_name"].astype(str).str.strip().str.split().str[-1].str.lower()
        )
    
        reminders_sorted = (
            reminders_sorted
            .sort_values(
                by=["_student_last_sort", "_faculty_last_sort", "student_name", "faculty_name"],
                ascending=True,
                kind="mergesort"
            )
            .drop(columns=["_student_last_sort", "_faculty_last_sort"])
        )
    
        # Preview only
        reminders_preview = reminders_sorted.copy()
        reminders_preview.insert(
            reminders_preview.columns.get_loc("faculty_name"),
            "student_last_name_debug",
            reminders_preview["student_name"].astype(str).str.split().str[-1]
        )
    
        st.dataframe(reminders_preview, use_container_width=True)
    
        # Clean Power Automate export columns only
        pa_cols = [
            "faculty_email",
            "faculty_name",
            "student_name",
            "evaluation_type",
            "expected_eval_count",
            "completed_eval_count",
            "pending_eval_count",
            "duplicate_match_flag",
            "reminder_note",
            "blank_form_link",
            "partial_form_link",
        ]
    
        csv_base = reminders_sorted[pa_cols].copy()
    
        cas_export = csv_base[
            csv_base["evaluation_type"]
            .astype(str)
            .str.contains("Clinical Assessment of Student", case=False, na=False)
        ].copy()
    
        hp_export = csv_base[
            csv_base["evaluation_type"]
            .astype(str)
            .str.contains("History Taking|Physical Exam|Observed H&P", case=False, na=False, regex=True)
        ].copy()
    
        st.download_button(
            label=f"Download preceptor_eval_reminders.csv ({len(cas_export)} rows)",
            data=cas_export.to_csv(index=False).encode("utf-8-sig"),
            file_name="preceptor_eval_reminders.csv",
            mime="text/csv",
        )
    
        st.download_button(
            label=f"Download observed_hp_reminders.csv ({len(hp_export)} rows)",
            data=hp_export.to_csv(index=False).encode("utf-8-sig"),
            file_name="observed_hp_reminders.csv",
            mime="text/csv",
        )
    
    with tab2:
        st.subheader("Separate files by evaluation type")
        if reminders.empty:
            st.info("No reminders to split.")
        else:
            for eval_type in sorted(reminders["evaluation_type"].dropna().unique().tolist()):
                sub = reminders[reminders["evaluation_type"].eq(eval_type)].copy()
                safe_name = re.sub(r"[^a-z0-9]+", "_", eval_type.lower()).strip("_") or "evaluation"
                st.write(f"**{eval_type}** — {len(sub)} reminder row(s)")
                st.dataframe(sub, use_container_width=True)
                st.download_button(
                    label=f"Download {safe_name}_reminders.csv",
                    data=sub.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"{safe_name}_reminders.csv",
                    mime="text/csv",
                    key=f"download_{safe_name}",
                )
    
    with tab3:
        st.subheader("All expected rows after matching")
        st.write(
            "Rows with `pending_eval_count = 0` matched a submitted OASIS evaluation. "
            "This tab is the best place to troubleshoot specific cases like Kaelor/Madeline."
        )
        st.dataframe(debug, use_container_width=True)
    
        debug_bytes = debug.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="Download debug_match_report.csv",
            data=debug_bytes,
            file_name="debug_match_report.csv",
            mime="text/csv",
        )
    
    with tab4:
        st.subheader("Normalized expected associations")
        st.dataframe(expected, use_container_width=True)
    
        st.subheader("Normalized completed OASIS submissions")
        st.dataframe(completed, use_container_width=True)
    
        st.download_button(
            label="Download normalized_expected_associations.csv",
            data=expected.to_csv(index=False).encode("utf-8-sig"),
            file_name="normalized_expected_associations.csv",
            mime="text/csv",
        )
        st.download_button(
            label="Download normalized_completed_oasis.csv",
            data=completed.to_csv(index=False).encode("utf-8-sig"),
            file_name="normalized_completed_oasis.csv",
            mime="text/csv",
        )
        
elif instrument == "Session Feedback Link Creator":
    st.header("📋 Session Feedback Link Creator")

    import io
    import json
    import base64
    import urllib.parse
    import requests
    import qrcode

    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.utils import ImageReader


    # =========================================================
    # SETTINGS
    # =========================================================

    BASE_SURVEY_URL = (
        "https://redcap.ctsi.psu.edu/surveys/"
        "?s=3HLWTMYWDF33479A"
    )

    GITHUB_DATA_FILE = "data/session_feedback_options.json"

    DEFAULT_SESSIONS = {
        "Conrad Krawiec": [
            "Residency Journal Club"
        ]
    }

    OTHER_OPTION = "➕ Other / enter manually"


    # =========================================================
    # GITHUB SETTINGS
    # =========================================================

    try:
        GITHUB_TOKEN = st.secrets["github"]["token"]
        GITHUB_REPO = st.secrets["github"]["repo"]
        GITHUB_BRANCH = st.secrets["github"].get("branch", "main")

        github_configured = True

    except Exception:
        GITHUB_TOKEN = ""
        GITHUB_REPO = ""
        GITHUB_BRANCH = "main"

        github_configured = False


    # =========================================================
    # GITHUB HELPER FUNCTIONS
    # =========================================================

    def github_headers():
        return {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }


    def github_file_url(file_path):
        encoded_path = urllib.parse.quote(
            file_path,
            safe="/"
        )

        return (
            f"https://api.github.com/repos/"
            f"{GITHUB_REPO}/contents/{encoded_path}"
        )


    def load_saved_sessions():
        """
        Load presenter/session data from GitHub.

        If the file does not exist yet, create it using
        DEFAULT_SESSIONS.
        """

        if not github_configured:
            return DEFAULT_SESSIONS.copy()

        url = github_file_url(GITHUB_DATA_FILE)

        try:
            response = requests.get(
                url,
                headers=github_headers(),
                params={"ref": GITHUB_BRANCH},
                timeout=15,
            )

            # File exists
            if response.status_code == 200:

                file_info = response.json()

                encoded_content = file_info.get(
                    "content",
                    ""
                )

                decoded_content = base64.b64decode(
                    encoded_content
                ).decode("utf-8")

                data = json.loads(decoded_content)

                if isinstance(data, dict):
                    return data

                return DEFAULT_SESSIONS.copy()

            # File does not exist yet
            elif response.status_code == 404:

                save_saved_sessions(
                    DEFAULT_SESSIONS,
                    commit_message=(
                        "Create session feedback options"
                    )
                )

                return DEFAULT_SESSIONS.copy()

            else:
                st.warning(
                    "Could not load saved presenters from "
                    f"GitHub. HTTP {response.status_code}"
                )

                return DEFAULT_SESSIONS.copy()

        except Exception as e:

            st.warning(
                "Could not load saved presenters. "
                f"Using defaults instead. {e}"
            )

            return DEFAULT_SESSIONS.copy()


    def save_saved_sessions(
        data,
        commit_message="Update session feedback options"
    ):
        """
        Create or update the JSON file in GitHub.
        """

        if not github_configured:
            st.error(
                "GitHub persistence is not configured. "
                "Add the GitHub settings to Streamlit Secrets."
            )
            return False

        url = github_file_url(GITHUB_DATA_FILE)

        sha = None

        try:
            # ---------------------------------------------
            # See if file already exists
            # ---------------------------------------------
            current_response = requests.get(
                url,
                headers=github_headers(),
                params={"ref": GITHUB_BRANCH},
                timeout=15,
            )

            if current_response.status_code == 200:
                sha = current_response.json().get("sha")

            elif current_response.status_code != 404:
                st.error(
                    "Could not check the existing GitHub file. "
                    f"HTTP {current_response.status_code}"
                )
                return False

            # ---------------------------------------------
            # Convert data to JSON
            # ---------------------------------------------
            json_text = json.dumps(
                data,
                indent=2,
                ensure_ascii=False
            )

            encoded_content = base64.b64encode(
                json_text.encode("utf-8")
            ).decode("utf-8")

            # ---------------------------------------------
            # GitHub PUT payload
            # ---------------------------------------------
            payload = {
                "message": commit_message,
                "content": encoded_content,
                "branch": GITHUB_BRANCH,
            }

            # Required when updating an existing file
            if sha:
                payload["sha"] = sha

            response = requests.put(
                url,
                headers=github_headers(),
                json=payload,
                timeout=15,
            )

            if response.status_code in (200, 201):
                return True

            st.error(
                "GitHub could not save the changes. "
                f"HTTP {response.status_code}: "
                f"{response.text}"
            )

            return False

        except Exception as e:

            st.error(
                f"Unable to save to GitHub: {e}"
            )

            return False


    # =========================================================
    # LOAD SAVED PRESENTERS / SESSIONS
    # =========================================================

    saved_sessions = load_saved_sessions()

    # Clean / sort loaded values
    cleaned_sessions = {}

    for person, titles in saved_sessions.items():

        person = str(person).strip()

        if not person:
            continue

        if not isinstance(titles, list):
            titles = [titles]

        cleaned_titles = sorted(
            {
                str(title).strip()
                for title in titles
                if str(title).strip()
            }
        )

        cleaned_sessions[person] = cleaned_titles

    saved_sessions = cleaned_sessions


    # =========================================================
    # SESSION INFORMATION
    # =========================================================

    st.subheader("Session Information")


    # ---------------------------------------------------------
    # PRESENTER
    # ---------------------------------------------------------

    presenter_options = (
        sorted(saved_sessions.keys())
        + [OTHER_OPTION]
    )

    selected_presenter = st.selectbox(
        "Presenter",
        options=presenter_options,
        index=None,
        placeholder="Select presenter..."
    )

    presenter = ""

    manual_presenter = False


    if selected_presenter == OTHER_OPTION:

        manual_presenter = True

        presenter = st.text_input(
            "Presenter name",
            value="",
            placeholder="Enter presenter name",
            key="manual_feedback_presenter"
        )

    elif selected_presenter:

        presenter = selected_presenter


    # ---------------------------------------------------------
    # SESSION TITLE
    # ---------------------------------------------------------

    session_title = ""
    manual_title = False


    if presenter:

        # Existing presenter
        if presenter in saved_sessions:

            title_options = (
                sorted(saved_sessions[presenter])
                + [OTHER_OPTION]
            )

            selected_title = st.selectbox(
                "Session Title",
                options=title_options,
                index=None,
                placeholder="Select session title..."
            )

            if selected_title == OTHER_OPTION:

                manual_title = True

                session_title = st.text_input(
                    "Session title",
                    value="",
                    placeholder="Enter session title",
                    key="manual_feedback_title"
                )

            elif selected_title:

                session_title = selected_title

        # Completely new presenter
        else:

            manual_title = True

            session_title = st.text_input(
                "Session Title",
                value="",
                placeholder="Enter session title",
                key="new_presenter_session_title"
            )

    else:

        st.selectbox(
            "Session Title",
            options=[],
            index=None,
            placeholder="Select a presenter first...",
            disabled=True
        )


    # ---------------------------------------------------------
    # DATE
    # ---------------------------------------------------------

    session_date = st.date_input(
        "Session Date",
        value=None,
        format="MM/DD/YYYY"
    )
    
    # REDCap requires M-D-Y with hyphens
    date_for_redcap = (
        session_date.strftime("%Y-%m-%d")
        if session_date
        else ""
    )
        
    # Friendly date for the PDF
    session_date_display = (
        session_date.strftime("%m/%d/%Y")
        if session_date
        else ""
    )


    # =========================================================
    # SAVE NEW PRESENTER / TITLE
    # =========================================================

    # Show save button whenever something was manually entered
    if (
        presenter.strip()
        and session_title.strip()
        and (manual_presenter or manual_title)
    ):

        if st.button(
            "💾 Save Presenter / Session for Future Use",
            use_container_width=True,
            key="save_feedback_presenter_session"
        ):

            presenter_clean = presenter.strip()
            title_clean = session_title.strip()

            # Reload before writing so we have the latest copy
            latest_sessions = load_saved_sessions()

            if presenter_clean not in latest_sessions:
                latest_sessions[presenter_clean] = []

            existing_titles = latest_sessions[
                presenter_clean
            ]

            if title_clean not in existing_titles:
                existing_titles.append(title_clean)

            latest_sessions[presenter_clean] = sorted(
                set(existing_titles)
            )

            success = save_saved_sessions(
                latest_sessions,
                commit_message=(
                    f"Add session feedback option: "
                    f"{presenter_clean} - {title_clean}"
                )
            )

            if success:
                st.success(
                    f"Saved {presenter_clean} — "
                    f"{title_clean}"
                )

                st.rerun()


    # =========================================================
    # CREATE FEEDBACK LINK
    # =========================================================

    if presenter.strip() and session_title.strip():

        params = {
            "presenter": presenter.strip(),
            "title": session_title.strip(),
        }

        if date_for_redcap:
            params["date"] = date_for_redcap

        encoded_params = urllib.parse.urlencode(params)

        feedback_url = (
            BASE_SURVEY_URL
            + "&"
            + encoded_params
        )


        # =====================================================
        # CREATE QR CODE
        # =====================================================

        qr = qrcode.QRCode(
            version=None,
            error_correction=(
                qrcode.constants.ERROR_CORRECT_M
            ),
            box_size=10,
            border=4,
        )

        qr.add_data(feedback_url)
        qr.make(fit=True)

        qr_image = qr.make_image(
            fill_color="black",
            back_color="white"
        )

        qr_buffer = io.BytesIO()

        qr_image.save(
            qr_buffer,
            format="PNG"
        )

        qr_buffer.seek(0)

        qr_bytes = qr_buffer.getvalue()


        # =====================================================
        # DISPLAY LINK + QR CODE
        # =====================================================

        st.divider()

        st.subheader("Student Feedback Link")

        st.image(
            qr_bytes,
            width=300
        )

        st.markdown(
            f"### [Open Session Feedback Survey]"
            f"({feedback_url})"
        )


        # =====================================================
        # CREATE PDF
        # =====================================================

        def create_feedback_pdf(
            presenter,
            session_title,
            session_date,
            feedback_url,
            qr_bytes
        ):

            pdf_buffer = io.BytesIO()

            c = canvas.Canvas(
                pdf_buffer,
                pagesize=letter
            )

            page_width, page_height = letter

            # ---------------------------------------------
            # Title
            # ---------------------------------------------
            c.setFont(
                "Helvetica-Bold",
                22
            )

            c.drawCentredString(
                page_width / 2,
                page_height - 90,
                "Session Feedback"
            )


            # ---------------------------------------------
            # Session title
            # ---------------------------------------------
            c.setFont(
                "Helvetica-Bold",
                16
            )

            c.drawCentredString(
                page_width / 2,
                page_height - 125,
                session_title
            )


            # ---------------------------------------------
            # Presenter
            # ---------------------------------------------
            c.setFont(
                "Helvetica",
                13
            )

            c.drawCentredString(
                page_width / 2,
                page_height - 150,
                presenter
            )


            # ---------------------------------------------
            # Date
            # ---------------------------------------------
            if session_date.strip():

                c.setFont(
                    "Helvetica",
                    12
                )

                c.drawCentredString(
                    page_width / 2,
                    page_height - 172,
                    session_date
                )


            # ---------------------------------------------
            # Instructions
            # ---------------------------------------------
            c.setFont(
                "Helvetica",
                13
            )

            c.drawCentredString(
                page_width / 2,
                page_height - 215,
                "Please scan the QR code to provide feedback."
            )


            # ---------------------------------------------
            # QR code
            # ---------------------------------------------
            qr_stream = io.BytesIO(qr_bytes)

            qr_reader = ImageReader(
                qr_stream
            )

            qr_size = 250

            c.drawImage(
                qr_reader,
                (page_width - qr_size) / 2,
                page_height - 500,
                width=qr_size,
                height=qr_size,
                preserveAspectRatio=True
            )


            # ---------------------------------------------
            # Clickable PDF link
            # ---------------------------------------------
            link_text = (
                "Click here to open the feedback survey"
            )

            c.setFont(
                "Helvetica-Bold",
                12
            )

            link_width = c.stringWidth(
                link_text,
                "Helvetica-Bold",
                12
            )

            link_x = (
                page_width - link_width
            ) / 2

            link_y = page_height - 535

            c.drawString(
                link_x,
                link_y,
                link_text
            )

            c.linkURL(
                feedback_url,
                (
                    link_x,
                    link_y - 3,
                    link_x + link_width,
                    link_y + 12
                ),
                relative=0
            )

            c.save()

            pdf_buffer.seek(0)

            return pdf_buffer.getvalue()


        pdf_bytes = create_feedback_pdf(
            presenter,
            session_title,
            session_date_display,
            feedback_url,
            qr_bytes
        )


        # =====================================================
        # DOWNLOAD PDF
        # =====================================================

        st.download_button(
            "📄 Download Feedback QR PDF",
            data=pdf_bytes,
            file_name="session_feedback_qr.pdf",
            mime="application/pdf",
            use_container_width=True
        )

    else:

        st.info(
            "Select or enter a presenter and session title "
            "to create the feedback link."
        )


    # =========================================================
    # MANAGE SAVED PRESENTERS
    # =========================================================

    with st.expander(
        "⚙️ Manage Saved Presenters & Sessions"
    ):

        if not github_configured:

            st.warning(
                "GitHub persistence is not configured yet. "
                "Add the [github] section to Streamlit Secrets."
            )

        elif not saved_sessions:

            st.info(
                "There are currently no saved presenters."
            )

        else:

            st.write(
                "Remove an individual session title or "
                "remove a presenter and all of their "
                "saved sessions."
            )


            # -------------------------------------------------
            # Select presenter to manage
            # -------------------------------------------------

            manage_presenter = st.selectbox(
                "Presenter to manage",
                options=sorted(
                    saved_sessions.keys()
                ),
                index=None,
                placeholder="Select presenter...",
                key="manage_feedback_presenter"
            )


            if manage_presenter:

                presenter_titles = saved_sessions.get(
                    manage_presenter,
                    []
                )


                # =============================================
                # REMOVE INDIVIDUAL SESSION
                # =============================================

                if presenter_titles:

                    remove_title = st.selectbox(
                        "Session title",
                        options=presenter_titles,
                        index=None,
                        placeholder=(
                            "Select session title..."
                        ),
                        key="remove_feedback_title"
                    )

                    if remove_title:

                        if st.button(
                            "🗑️ Remove This Session",
                            use_container_width=True,
                            key="remove_feedback_session"
                        ):

                            latest_sessions = (
                                load_saved_sessions()
                            )

                            if (
                                manage_presenter
                                in latest_sessions
                            ):

                                latest_sessions[
                                    manage_presenter
                                ] = [
                                    title
                                    for title
                                    in latest_sessions[
                                        manage_presenter
                                    ]
                                    if title != remove_title
                                ]

                                # If no titles remain,
                                # remove presenter
                                if not latest_sessions[
                                    manage_presenter
                                ]:
                                    del latest_sessions[
                                        manage_presenter
                                    ]

                            success = save_saved_sessions(
                                latest_sessions,
                                commit_message=(
                                    "Remove session feedback "
                                    f"option: "
                                    f"{manage_presenter} - "
                                    f"{remove_title}"
                                )
                            )

                            if success:

                                st.success(
                                    "Session removed."
                                )

                                st.rerun()


                # =============================================
                # REMOVE ENTIRE PRESENTER
                # =============================================

                st.divider()

                remove_entire_presenter = (
                    st.checkbox(
                        f"Remove {manage_presenter} "
                        "and all saved session titles",
                        key=(
                            "confirm_remove_"
                            "feedback_presenter"
                        )
                    )
                )

                if remove_entire_presenter:

                    if st.button(
                        "🗑️ Remove Presenter",
                        type="primary",
                        use_container_width=True,
                        key=(
                            "remove_entire_"
                            "feedback_presenter"
                        )
                    ):

                        latest_sessions = (
                            load_saved_sessions()
                        )

                        if (
                            manage_presenter
                            in latest_sessions
                        ):

                            del latest_sessions[
                                manage_presenter
                            ]

                        success = save_saved_sessions(
                            latest_sessions,
                            commit_message=(
                                "Remove session feedback "
                                f"presenter: "
                                f"{manage_presenter}"
                            )
                        )

                        if success:

                            st.success(
                                f"{manage_presenter} removed."
                            )

                            st.rerun()

elif instrument == "Session Feedback Summary Creator":
    st.header("📋 Session Feedback Summary Creator")

    import io
    import re
    import html
    import zipfile
    import hashlib
    import pandas as pd

    from docx import Document
    from docx.shared import Inches, Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import (
        WD_TABLE_ALIGNMENT,
        WD_CELL_VERTICAL_ALIGNMENT
    )
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn


    # =========================================================
    # DEFAULT QUESTION / COMMENT LABELS
    # =========================================================
    #
    # These are only starting labels.
    #
    # You will ALSO be able to edit the wording directly
    # in the app after uploading the REDCap file.
    #
    # Therefore, if your REDCap questions change later,
    # you do not have to rewrite the report code.
    # =========================================================

    DEFAULT_QUESTION_LABELS = {
        "q001": "The presenter was well-prepared for this session.",
        "q002": "The presenter created an environment that encouraged me to participate and ask questions.",
        "q003": "I gained knowledge or skills from this session that I expect to use in future clinical encounters.",
        "q004": "The cases or examples used by the presenter enhanced my understanding of the material.",
        "q005": "This presenter modeled effective clinical reasoning to help me develop my own clinical reasoning.",
        "q006": "This presenter contributed meaningfully to my learning during the pediatric clerkship.",
        "q007": "This presenter was an effective educator during my time in the pediatric clerkship.",
        "q008": "Overall, I found this teaching session valuable to my learning.",
    }

    DEFAULT_COMMENT_LABELS = {
        "session_c001": "What is one aspect of the session that contributed most to your learning?",
        "session_c002": "What suggestions would you offer to further enhance the teaching session?",
    }


    # =========================================================
    # HELPER FUNCTIONS
    # =========================================================

    def get_academic_year(value):
        """
        Academic year starts July 1.

        Examples:
        09/10/2026 -> 2026-2027
        03/10/2027 -> 2026-2027
        """

        d = pd.to_datetime(
            value,
            errors="coerce"
        )

        if pd.isna(d):
            return "Unknown"

        if d.month >= 7:
            return f"{d.year}-{d.year + 1}"

        return f"{d.year - 1}-{d.year}"


    def clean_redcap_comment(value):
        """
        Remove REDCap HTML formatting from narrative comments.
        """

        if pd.isna(value):
            return ""

        text = html.unescape(
            str(value)
        )

        text = re.sub(
            r"<br\s*/?>",
            "\n",
            text,
            flags=re.IGNORECASE
        )

        text = re.sub(
            r"</p\s*>",
            "\n",
            text,
            flags=re.IGNORECASE
        )

        text = re.sub(
            r"<[^>]+>",
            "",
            text
        )

        text = text.replace(
            "\xa0",
            " "
        )

        text = re.sub(
            r"[ \t]+",
            " ",
            text
        )

        text = re.sub(
            r"\n\s*\n+",
            "\n",
            text
        )

        return text.strip()


    def safe_filename(value):

        value = re.sub(
            r"[^A-Za-z0-9._ -]",
            "",
            str(value)
        )

        value = value.strip().replace(
            " ",
            "_"
        )

        return value or "Presenter"


    def numeric_field_sort(field_name):
        """
        Keeps q001, q002, q003 ... q010 in the correct order.
        """

        match = re.search(
            r"(\d+)$",
            str(field_name)
        )

        if match:
            return int(
                match.group(1)
            )

        return 9999


    # =========================================================
    # WORD FORMATTING HELPERS
    # =========================================================

    def shade_cell(
        cell,
        fill="D9E1F2"
    ):

        tc_pr = cell._tc.get_or_add_tcPr()

        shading = tc_pr.find(
            qn("w:shd")
        )

        if shading is None:

            shading = OxmlElement(
                "w:shd"
            )

            tc_pr.append(
                shading
            )

        shading.set(
            qn("w:fill"),
            fill
        )


    def set_cell_text(
        cell,
        text,
        bold=False,
        size=9,
        alignment="center"
    ):

        cell.text = ""

        paragraph = cell.paragraphs[0]

        if alignment == "left":
            paragraph.alignment = (
                WD_ALIGN_PARAGRAPH.LEFT
            )
        else:
            paragraph.alignment = (
                WD_ALIGN_PARAGRAPH.CENTER
            )

        paragraph.paragraph_format.space_after = Pt(0)

        run = paragraph.add_run(
            str(text)
        )

        run.bold = bold
        run.font.name = "Arial"
        run.font.size = Pt(size)

        cell.vertical_alignment = (
            WD_CELL_VERTICAL_ALIGNMENT.CENTER
        )


    def add_section_heading(
        document,
        text
    ):

        paragraph = document.add_paragraph()

        paragraph.paragraph_format.space_before = Pt(8)
        paragraph.paragraph_format.space_after = Pt(3)

        run = paragraph.add_run(
            text
        )

        run.bold = True
        run.underline = True
        run.font.name = "Arial"
        run.font.size = Pt(11)


    # =========================================================
    # CREATE PRESENTER DATA
    # =========================================================

    def prepare_presenter_data(
        evaluation_df,
        presenter_name,
        question_columns
    ):

        presenter_df = evaluation_df[
            evaluation_df["presenter"]
            .astype(str)
            .str.strip()
            == presenter_name
        ].copy()


        # -----------------------------------------------------
        # Convert rating questions to numbers
        # -----------------------------------------------------

        for col in question_columns:

            presenter_df[col] = pd.to_numeric(
                presenter_df[col],
                errors="coerce"
            )


        # -----------------------------------------------------
        # Session date
        # -----------------------------------------------------

        if "date" in presenter_df.columns:

            presenter_df["_session_date"] = pd.to_datetime(
                presenter_df["date"],
                errors="coerce"
            )

        else:

            presenter_df["_session_date"] = pd.NaT


        # -----------------------------------------------------
        # If date was missing, use REDCap timestamp as fallback
        # -----------------------------------------------------

        if "form_1_timestamp" in presenter_df.columns:

            timestamp_date = pd.to_datetime(
                presenter_df["form_1_timestamp"],
                errors="coerce"
            )

            presenter_df[
                "_session_date"
            ] = presenter_df[
                "_session_date"
            ].fillna(
                timestamp_date
            )


        # -----------------------------------------------------
        # Academic year
        # -----------------------------------------------------

        presenter_df[
            "_academic_year"
        ] = presenter_df[
            "_session_date"
        ].apply(
            get_academic_year
        )


        # -----------------------------------------------------
        # Clean session title
        # -----------------------------------------------------

        presenter_df["_title"] = (
            presenter_df["title"]
            .fillna("Untitled Session")
            .astype(str)
            .str.strip()
        )

        presenter_df.loc[
            presenter_df["_title"] == "",
            "_title"
        ] = "Untitled Session"


        # -----------------------------------------------------
        # SESSION COUNT
        #
        # One unique:
        #
        # Presenter + Session Title + Date
        #
        # = one session delivered.
        #
        # Therefore 15 evaluations from one session still
        # count as ONE session.
        # -----------------------------------------------------

        presenter_df[
            "_session_day"
        ] = presenter_df[
            "_session_date"
        ].dt.strftime(
            "%Y-%m-%d"
        )

        presenter_df[
            "_session_day"
        ] = presenter_df[
            "_session_day"
        ].fillna(
            "Unknown"
        )

        presenter_df[
            "_session_key"
        ] = (
            presenter_df["_title"]
            + "||"
            + presenter_df["_session_day"]
        )

        return presenter_df


    # =========================================================
    # INDIVIDUAL SESSION SUMMARY TABLE
    # =========================================================

    def create_session_summary(
        presenter_df,
        question_columns
    ):

        summary_rows = []

        # -----------------------------------------------------
        # Each unique date + title = one individual session
        #
        # Multiple learner evaluations from that session
        # are grouped together into the same row.
        # -----------------------------------------------------

        grouped = presenter_df.groupby(
            [
                "_academic_year",
                "_session_day",
                "_title"
            ],
            dropna=False
        )


        for (
            academic_year,
            session_day,
            session_title
        ), group in grouped:


            # -------------------------------------------------
            # Average rating for THIS individual session
            # -------------------------------------------------

            if question_columns:

                scores = (
                    group[
                        question_columns
                    ]
                    .stack()
                    .dropna()
                )

            else:

                scores = pd.Series(
                    dtype=float
                )


            if len(scores) > 0:

                rating_average = float(
                    scores.mean()
                )

            else:

                rating_average = None


            # -------------------------------------------------
            # Number of evaluations submitted for this session
            # -------------------------------------------------

            number_evaluations = len(
                group
            )


            # -------------------------------------------------
            # Participant number
            #
            # par_number should normally be identical on every
            # evaluation from the same session.
            #
            # Use the first valid value.
            # -------------------------------------------------

            participant_number = None

            if "par_number" in group.columns:

                participant_values = pd.to_numeric(
                    group["par_number"],
                    errors="coerce"
                ).dropna()

                if len(participant_values) > 0:

                    participant_number = int(
                        participant_values.iloc[0]
                    )


            # -------------------------------------------------
            # Friendly date
            # -------------------------------------------------

            parsed_date = pd.to_datetime(
                session_day,
                errors="coerce"
            )

            if pd.isna(parsed_date):

                display_date = ""

            else:

                display_date = parsed_date.strftime(
                    "%m/%d/%Y"
                )


            summary_rows.append(
                {
                    "Academic Year":
                        academic_year,

                    "Session Date":
                        display_date,

                    "Session Title":
                        session_title,

                    "Participants":
                        participant_number,

                    "Rating Average":
                        rating_average,

                    "Number of Evaluations":
                        number_evaluations,
                }
            )


        summary_df = pd.DataFrame(
            summary_rows
        )


        # -----------------------------------------------------
        # Sort newest sessions first
        # -----------------------------------------------------

        if not summary_df.empty:

            summary_df[
                "_sort_date"
            ] = pd.to_datetime(
                summary_df[
                    "Session Date"
                ],
                errors="coerce"
            )

            summary_df = summary_df.sort_values(
                "_sort_date",
                ascending=False
            )

            summary_df = summary_df.drop(
                columns=[
                    "_sort_date"
                ]
            )


        return summary_df

    # =========================================================
    # CREATE WORD DOCUMENT
    # =========================================================

    def create_presenter_word_report(
        evaluation_df,
        presenter_name,
        question_columns,
        question_labels,
        comment_columns,
        comment_labels,
        custom_comment_summary=""
    ):

        presenter_df = prepare_presenter_data(
            evaluation_df,
            presenter_name,
            question_columns
        )

        session_summary = create_session_summary(
            presenter_df,
            question_columns
        )


        # =====================================================
        # OVERALL SCORE
        # =====================================================

        if question_columns:

            all_scores = (
                presenter_df[
                    question_columns
                ]
                .stack()
                .dropna()
            )

        else:

            all_scores = pd.Series(
                dtype=float
            )


        if len(all_scores) > 0:

            overall_rating = float(
                all_scores.mean()
            )

            overall_rating_text = (
                f"{overall_rating:.2f}/5.00"
            )

        else:

            overall_rating = None
            overall_rating_text = "N/A"


        total_evaluations = len(
            presenter_df
        )


        # =====================================================
        # COMMENTS
        # =====================================================

        cleaned_comments = {}

        evaluations_with_comments = pd.Series(
            False,
            index=presenter_df.index
        )

        total_comments = 0


        for comment_col in comment_columns:

            entries = []

            for idx, row in presenter_df.iterrows():

                comment = clean_redcap_comment(
                    row.get(
                        comment_col,
                        ""
                    )
                )

                if not comment:
                    continue


                total_comments += 1

                evaluations_with_comments.loc[
                    idx
                ] = True


                session_date = pd.to_datetime(
                    row.get(
                        "_session_date"
                    ),
                    errors="coerce"
                )


                if pd.isna(
                    session_date
                ):

                    date_text = ""

                else:

                    date_text = session_date.strftime(
                        "%m/%d/%Y"
                    )


                entries.append(
                    {
                        "date":
                            date_text,

                        "title":
                            row.get(
                                "_title",
                                ""
                            ),

                        "comment":
                            comment,
                    }
                )


            cleaned_comments[
                comment_col
            ] = entries


        number_evaluations_with_comments = int(
            evaluations_with_comments.sum()
        )


        # =====================================================
        # WORD DOCUMENT
        # =====================================================

        document = Document()

        section = document.sections[0]

        section.top_margin = Inches(0.55)
        section.bottom_margin = Inches(0.55)
        section.left_margin = Inches(0.55)
        section.right_margin = Inches(0.55)


        # -----------------------------------------------------
        # Default font
        # -----------------------------------------------------

        normal_style = document.styles[
            "Normal"
        ]

        normal_style.font.name = "Arial"
        normal_style.font.size = Pt(9)


        # =====================================================
        # PRESENTER NAME
        # =====================================================

        paragraph = document.add_paragraph()

        paragraph.alignment = (
            WD_ALIGN_PARAGRAPH.CENTER
        )

        paragraph.paragraph_format.space_after = Pt(
            2
        )

        run = paragraph.add_run(
            presenter_name
        )

        run.bold = True
        run.font.name = "Arial"
        run.font.size = Pt(16)


        # =====================================================
        # TITLE
        # =====================================================

        paragraph = document.add_paragraph()

        paragraph.alignment = (
            WD_ALIGN_PARAGRAPH.CENTER
        )

        paragraph.paragraph_format.space_after = Pt(
            7
        )

        run = paragraph.add_run(
            "Teaching Evaluation Summary"
        )

        run.bold = True
        run.font.name = "Arial"
        run.font.size = Pt(12)


        # =====================================================
        # OVERALL SUMMARY
        # =====================================================

        paragraph = document.add_paragraph()

        paragraph.alignment = (
            WD_ALIGN_PARAGRAPH.CENTER
        )

        paragraph.paragraph_format.space_after = Pt(
            8
        )

        run = paragraph.add_run(
            f"Completed Evaluations: {total_evaluations}"
            f"    |    "
            f"Overall Rating: {overall_rating_text}"
        )

        run.font.name = "Arial"
        run.font.size = Pt(9)


        # =====================================================
        # TEACHING ACTIVITY SUMMARY
        # =====================================================

        add_section_heading(
            document,
            "Teaching Activity Summary"
        )


        activity_table = document.add_table(
            rows=1,
            cols=6
        )

        activity_table.style = "Table Grid"

        activity_table.alignment = (
            WD_TABLE_ALIGNMENT.CENTER
        )

        activity_table.autofit = True


        activity_headers = [
            "Academic Year",
            "Session Date",
            "Session Title",
            "Participants",
            "Rating Average\nLow 1 - High 5",
            "Number of\nEvaluations",
        ]

        for index, header in enumerate(
            activity_headers
        ):

            shade_cell(
                activity_table.rows[
                    0
                ].cells[index]
            )

            set_cell_text(
                activity_table.rows[
                    0
                ].cells[index],
                header,
                bold=True,
                size=8
            )


        for _, row in session_summary.iterrows():

            cells = activity_table.add_row().cells


            # ---------------------------------------------
            # Rating
            # ---------------------------------------------

            rating = row[
                "Rating Average"
            ]

            if pd.isna(rating):

                rating_text = "N/A"

            else:

                rating_text = (
                    f"{rating:.2f}"
                )


            # ---------------------------------------------
            # Participants
            # ---------------------------------------------

            participants = row[
                "Participants"
            ]

            if pd.isna(participants):

                participant_text = ""

            else:

                participant_text = str(
                    int(participants)
                )


            # ---------------------------------------------
            # Row values
            # ---------------------------------------------

            values = [
                row[
                    "Academic Year"
                ],

                row[
                    "Session Date"
                ],

                row[
                    "Session Title"
                ],

                participant_text,

                rating_text,

                int(
                    row[
                        "Number of Evaluations"
                    ]
                ),
            ]


            for index, value in enumerate(
                values
            ):

                set_cell_text(
                    cells[index],
                    value,
                    size=8,
                    alignment=(
                        "left"
                        if index == 2
                        else "center"
                    )
                )


        # =====================================================
        # TEACHING EVALUATIONS — QUESTION AVERAGES
        # =====================================================

        add_section_heading(
            document,
            "Teaching Evaluations"
        )


        if question_columns:

            question_table = document.add_table(
                rows=1,
                cols=3
            )

            question_table.style = "Table Grid"

            question_table.alignment = (
                WD_TABLE_ALIGNMENT.CENTER
            )


            question_headers = [
                "Evaluation Item",
                (
                    "Average Response\n"
                    "1 = Low / Strongly Disagree\n"
                    "5 = High / Strongly Agree"
                ),
                "N",
            ]


            for index, header in enumerate(
                question_headers
            ):

                shade_cell(
                    question_table.rows[
                        0
                    ].cells[index]
                )

                set_cell_text(
                    question_table.rows[
                        0
                    ].cells[index],
                    header,
                    bold=True,
                    size=8
                )


            for question_col in question_columns:

                values = pd.to_numeric(
                    presenter_df[
                        question_col
                    ],
                    errors="coerce"
                ).dropna()


                if len(values) > 0:

                    average_text = (
                        f"{values.mean():.2f}"
                    )

                else:

                    average_text = "N/A"


                cells = (
                    question_table
                    .add_row()
                    .cells
                )


                set_cell_text(
                    cells[0],
                    question_labels.get(
                        question_col,
                        question_col
                    ),
                    size=8,
                    alignment="left"
                )

                set_cell_text(
                    cells[1],
                    average_text,
                    size=8
                )

                set_cell_text(
                    cells[2],
                    len(values),
                    size=8
                )

        else:

            paragraph = document.add_paragraph(
                "No rating questions were detected."
            )

            paragraph.runs[
                0
            ].font.size = Pt(8.5)


        # =====================================================
        # NARRATIVE FEEDBACK SUMMARY
        # =====================================================

        add_section_heading(
            document,
            "Narrative Feedback Summary"
        )


        # -----------------------------------------------------
        # Optional custom summary
        # -----------------------------------------------------

        if custom_comment_summary.strip():

            paragraph = document.add_paragraph()

            paragraph.paragraph_format.space_after = Pt(
                5
            )

            run = paragraph.add_run(
                custom_comment_summary.strip()
            )

            run.font.name = "Arial"
            run.font.size = Pt(9)

        else:

            # Factual automatic summary
            paragraph = document.add_paragraph()

            paragraph.paragraph_format.space_after = Pt(
                5
            )

            run = paragraph.add_run(
                f"Written feedback was provided on "
                f"{number_evaluations_with_comments} of "
                f"{total_evaluations} completed evaluations. "
                f"A total of {total_comments} narrative "
                f"comment(s) were submitted."
            )

            run.font.name = "Arial"
            run.font.size = Pt(9)


        # -----------------------------------------------------
        # Comment counts by question/prompt
        # -----------------------------------------------------

        if comment_columns:

            comment_summary_table = document.add_table(
                rows=1,
                cols=2
            )

            comment_summary_table.style = (
                "Table Grid"
            )

            comment_summary_table.alignment = (
                WD_TABLE_ALIGNMENT.CENTER
            )


            shade_cell(
                comment_summary_table.rows[
                    0
                ].cells[0]
            )

            shade_cell(
                comment_summary_table.rows[
                    0
                ].cells[1]
            )


            set_cell_text(
                comment_summary_table.rows[
                    0
                ].cells[0],
                "Narrative Feedback Item",
                bold=True,
                size=8
            )

            set_cell_text(
                comment_summary_table.rows[
                    0
                ].cells[1],
                "Comments Submitted",
                bold=True,
                size=8
            )


            for comment_col in comment_columns:

                cells = (
                    comment_summary_table
                    .add_row()
                    .cells
                )


                set_cell_text(
                    cells[0],
                    comment_labels.get(
                        comment_col,
                        comment_col
                    ),
                    size=8,
                    alignment="left"
                )

                set_cell_text(
                    cells[1],
                    len(
                        cleaned_comments.get(
                            comment_col,
                            []
                        )
                    ),
                    size=8
                )


        # =====================================================
        # VERBATIM COMMENTS
        # =====================================================

        add_section_heading(
            document,
            "Learner Comments"
        )


        comments_written = False


        for comment_col in comment_columns:

            entries = cleaned_comments.get(
                comment_col,
                []
            )


            if not entries:
                continue


            comments_written = True


            # ---------------------------------------------
            # Prompt heading
            # ---------------------------------------------

            paragraph = document.add_paragraph()

            paragraph.paragraph_format.space_before = Pt(
                4
            )

            paragraph.paragraph_format.space_after = Pt(
                1
            )

            run = paragraph.add_run(
                comment_labels.get(
                    comment_col,
                    comment_col
                )
            )

            run.bold = True
            run.font.name = "Arial"
            run.font.size = Pt(9)


            # ---------------------------------------------
            # Individual comments
            # ---------------------------------------------

            for entry in entries:

                context = []

                if entry["date"]:
                    context.append(
                        entry["date"]
                    )

                if entry["title"]:
                    context.append(
                        entry["title"]
                    )


                if context:

                    prefix = (
                        " — ".join(
                            context
                        )
                        + ": "
                    )

                else:

                    prefix = ""


                paragraph = document.add_paragraph(
                    style="List Bullet"
                )

                paragraph.paragraph_format.space_after = Pt(
                    1
                )

                run = paragraph.add_run(
                    prefix
                    + entry["comment"]
                )

                run.font.name = "Arial"
                run.font.size = Pt(8.5)


        if not comments_written:

            paragraph = document.add_paragraph(
                "No narrative comments were submitted."
            )

            paragraph.runs[
                0
            ].font.size = Pt(8.5)


        # -----------------------------------------------------
        # Note
        # -----------------------------------------------------

        paragraph = document.add_paragraph()

        paragraph.paragraph_format.space_before = Pt(
            6
        )

        run = paragraph.add_run(
            "Learner comments are presented verbatim "
            "except for removal of REDCap HTML formatting."
        )

        run.italic = True
        run.font.name = "Arial"
        run.font.size = Pt(7.5)


        # =====================================================
        # SAVE WORD FILE TO MEMORY
        # =====================================================

        output = io.BytesIO()

        document.save(
            output
        )

        output.seek(0)

        return output.getvalue()


    # =========================================================
    # USER INTERFACE
    # =========================================================

    st.write(
        "Upload the REDCap CSV export to create "
        "promotion-ready teaching evaluation summaries "
        "for each presenter."
    )

    st.caption(
        "A session is counted once for each unique "
        "presenter + session title + session date. "
        "Multiple learner evaluations from the same session "
        "do not increase the session count."
    )


    # =========================================================
    # UPLOAD REDCAP FILE
    # =========================================================

    uploaded_file = st.file_uploader(
        "Upload REDCap Evaluation CSV",
        type=["csv"],
        key="session_feedback_summary_upload"
    )


    if uploaded_file is not None:

        # -----------------------------------------------------
        # Read file
        # -----------------------------------------------------

        file_bytes = uploaded_file.getvalue()

        current_file_hash = hashlib.sha256(
            file_bytes
        ).hexdigest()


        # Clear old generated reports when a new file is uploaded
        if (
            st.session_state.get(
                "feedback_summary_file_hash"
            )
            != current_file_hash
        ):

            st.session_state[
                "feedback_summary_file_hash"
            ] = current_file_hash

            st.session_state.pop(
                "feedback_summary_reports",
                None
            )

            st.session_state.pop(
                "feedback_summary_zip",
                None
            )


        try:

            evaluation_df = pd.read_csv(
                io.BytesIO(
                    file_bytes
                )
            )

        except Exception as e:

            st.error(
                f"Could not read the REDCap CSV: {e}"
            )

            evaluation_df = None


        if evaluation_df is not None:

            # =================================================
            # VALIDATE REQUIRED FIELDS
            # =================================================

            required_columns = {
                "presenter",
                "title",
                "date",
                "par_number"
            }

            missing_columns = (
                required_columns
                - set(
                    evaluation_df.columns
                )
            )


            if missing_columns:

                st.error(
                    "The REDCap export is missing required "
                    "column(s): "
                    + ", ".join(
                        sorted(
                            missing_columns
                        )
                    )
                )

            else:

                # =============================================
                # COMPLETED EVALUATIONS ONLY
                # =============================================

                if (
                    "form_1_complete"
                    in evaluation_df.columns
                ):

                    evaluation_df[
                        "form_1_complete"
                    ] = pd.to_numeric(
                        evaluation_df[
                            "form_1_complete"
                        ],
                        errors="coerce"
                    )

                    original_count = len(
                        evaluation_df
                    )

                    evaluation_df = (
                        evaluation_df[
                            evaluation_df[
                                "form_1_complete"
                            ] == 2
                        ]
                        .copy()
                    )

                    removed_count = (
                        original_count
                        - len(
                            evaluation_df
                        )
                    )


                    if removed_count > 0:

                        st.caption(
                            f"{removed_count} incomplete or "
                            "unverified evaluation(s) excluded."
                        )


                # =============================================
                # CLEAN PRESENTER NAMES
                # =============================================

                evaluation_df = evaluation_df[
                    evaluation_df[
                        "presenter"
                    ].notna()
                ].copy()


                evaluation_df[
                    "presenter"
                ] = (
                    evaluation_df[
                        "presenter"
                    ]
                    .astype(str)
                    .str.strip()
                )


                evaluation_df = evaluation_df[
                    evaluation_df[
                        "presenter"
                    ] != ""
                ].copy()


                # =============================================
                # DETECT RATING QUESTIONS
                # =============================================

                detected_questions = sorted(
                    [
                        col
                        for col in evaluation_df.columns
                        if re.fullmatch(
                            r"q\d+",
                            str(col)
                        )
                    ],
                    key=numeric_field_sort
                )


                # =============================================
                # DETECT COMMENT FIELDS
                # =============================================

                detected_comments = sorted(
                    [
                        col
                        for col in evaluation_df.columns
                        if re.fullmatch(
                            r"session_c\d+",
                            str(col)
                        )
                    ],
                    key=numeric_field_sort
                )


                # =============================================
                # UPLOAD SUMMARY
                # =============================================

                presenter_list = sorted(
                    evaluation_df[
                        "presenter"
                    ]
                    .dropna()
                    .unique()
                    .tolist()
                )


                col1, col2, col3 = st.columns(
                    3
                )

                col1.metric(
                    "Presenters",
                    len(
                        presenter_list
                    )
                )

                col2.metric(
                    "Completed Evaluations",
                    len(
                        evaluation_df
                    )
                )

                col3.metric(
                    "Rating Questions",
                    len(
                        detected_questions
                    )
                )


                # =============================================
                # QUESTION LABEL EDITOR
                # =============================================

                st.subheader(
                    "Evaluation Questions"
                )

                st.caption(
                    "The REDCap variable names are detected "
                    "automatically. Edit the question wording "
                    "below whenever your survey changes."
                )


                if detected_questions:

                    question_config = pd.DataFrame(
                        {
                            "Include": [
                                True
                                for _ in detected_questions
                            ],

                            "REDCap Field":
                                detected_questions,

                            "Question / Evaluation Item":
                                [
                                    DEFAULT_QUESTION_LABELS.get(
                                        field,
                                        field
                                    )
                                    for field
                                    in detected_questions
                                ],
                        }
                    )


                    edited_question_config = st.data_editor(
                        question_config,
                        hide_index=True,
                        use_container_width=True,
                        disabled=[
                            "REDCap Field"
                        ],
                        key=(
                            "feedback_summary_"
                            "question_editor"
                        )
                    )


                    included_question_rows = (
                        edited_question_config[
                            edited_question_config[
                                "Include"
                            ] == True
                        ]
                    )


                    question_columns = (
                        included_question_rows[
                            "REDCap Field"
                        ]
                        .tolist()
                    )


                    question_labels = dict(
                        zip(
                            included_question_rows[
                                "REDCap Field"
                            ],

                            included_question_rows[
                                "Question / Evaluation Item"
                            ]
                        )
                    )

                else:

                    question_columns = []
                    question_labels = {}

                    st.warning(
                        "No q### rating fields were detected."
                    )


                # =============================================
                # COMMENT LABEL EDITOR
                # =============================================

                st.subheader(
                    "Narrative Comment Questions"
                )


                if detected_comments:

                    comment_config = pd.DataFrame(
                        {
                            "Include": [
                                True
                                for _ in detected_comments
                            ],

                            "REDCap Field":
                                detected_comments,

                            "Comment Prompt":
                                [
                                    DEFAULT_COMMENT_LABELS.get(
                                        field,
                                        field
                                    )
                                    for field
                                    in detected_comments
                                ],
                        }
                    )


                    edited_comment_config = st.data_editor(
                        comment_config,
                        hide_index=True,
                        use_container_width=True,
                        disabled=[
                            "REDCap Field"
                        ],
                        key=(
                            "feedback_summary_"
                            "comment_editor"
                        )
                    )


                    included_comment_rows = (
                        edited_comment_config[
                            edited_comment_config[
                                "Include"
                            ] == True
                        ]
                    )


                    comment_columns = (
                        included_comment_rows[
                            "REDCap Field"
                        ]
                        .tolist()
                    )


                    comment_labels = dict(
                        zip(
                            included_comment_rows[
                                "REDCap Field"
                            ],

                            included_comment_rows[
                                "Comment Prompt"
                            ]
                        )
                    )

                else:

                    comment_columns = []
                    comment_labels = {}

                    st.info(
                        "No narrative comment fields "
                        "were detected."
                    )


                # =============================================
                # SELECT PRESENTERS
                # =============================================

                st.subheader(
                    "Presenters"
                )


                presenters_to_generate = st.multiselect(
                    "Presenters to include",
                    options=presenter_list,
                    default=presenter_list,
                    key=(
                        "feedback_summary_"
                        "presenter_selection"
                    )
                )


                # =============================================
                # OPTIONAL COMMENT SUMMARIES
                # =============================================

                custom_comment_summaries = {}


                if presenters_to_generate:

                    with st.expander(
                        "✏️ Optional Narrative Comment Summaries"
                    ):

                        st.caption(
                            "Optional. Leave these blank and "
                            "the report will automatically state "
                            "how many evaluations contained written "
                            "feedback and how many comments were "
                            "submitted. You can also type a brief "
                            "promotion-ready thematic summary here."
                        )


                        for person in presenters_to_generate:

                            custom_comment_summaries[
                                person
                            ] = st.text_area(
                                f"{person}",
                                value="",
                                placeholder=(
                                    "Optional summary of recurring "
                                    "strengths, themes, or suggestions..."
                                ),
                                key=(
                                    "feedback_comment_summary_"
                                    + safe_filename(
                                        person
                                    )
                                )
                            )


                # =============================================
                # GENERATE WORD DOCUMENTS
                # =============================================

                if st.button(
                    "📄 Create Presenter Word Summaries",
                    type="primary",
                    use_container_width=True,
                    key=(
                        "create_session_feedback_"
                        "summary_reports"
                    )
                ):

                    if not presenters_to_generate:

                        st.warning(
                            "Select at least one presenter."
                        )

                    else:

                        generated_reports = {}


                        for presenter_name in (
                            presenters_to_generate
                        ):

                            report_bytes = (
                                create_presenter_word_report(
                                    evaluation_df=(
                                        evaluation_df
                                    ),

                                    presenter_name=(
                                        presenter_name
                                    ),

                                    question_columns=(
                                        question_columns
                                    ),

                                    question_labels=(
                                        question_labels
                                    ),

                                    comment_columns=(
                                        comment_columns
                                    ),

                                    comment_labels=(
                                        comment_labels
                                    ),

                                    custom_comment_summary=(
                                        custom_comment_summaries
                                        .get(
                                            presenter_name,
                                            ""
                                        )
                                    ),
                                )
                            )


                            filename = (
                                safe_filename(
                                    presenter_name
                                )
                                + "_Teaching_Evaluation_"
                                + "Summary.docx"
                            )


                            generated_reports[
                                presenter_name
                            ] = {
                                "filename":
                                    filename,

                                "bytes":
                                    report_bytes,
                            }


                        # =====================================
                        # ZIP ALL REPORTS
                        # =====================================

                        zip_buffer = io.BytesIO()


                        with zipfile.ZipFile(
                            zip_buffer,
                            mode="w",
                            compression=(
                                zipfile.ZIP_DEFLATED
                            )
                        ) as zip_file:

                            for report_data in (
                                generated_reports.values()
                            ):

                                zip_file.writestr(
                                    report_data[
                                        "filename"
                                    ],
                                    report_data[
                                        "bytes"
                                    ]
                                )


                        zip_buffer.seek(0)


                        st.session_state[
                            "feedback_summary_reports"
                        ] = generated_reports

                        st.session_state[
                            "feedback_summary_zip"
                        ] = zip_buffer.getvalue()


                # =============================================
                # DOWNLOAD REPORTS
                # =============================================

                if (
                    "feedback_summary_reports"
                    in st.session_state
                ):

                    reports = st.session_state[
                        "feedback_summary_reports"
                    ]


                    st.success(
                        f"Created {len(reports)} "
                        "presenter Word summary file(s)."
                    )


                    for (
                        presenter_name,
                        report_data
                    ) in reports.items():

                        st.download_button(
                            label=(
                                "⬇️ Download "
                                f"{presenter_name}"
                            ),

                            data=(
                                report_data[
                                    "bytes"
                                ]
                            ),

                            file_name=(
                                report_data[
                                    "filename"
                                ]
                            ),

                            mime=(
                                "application/"
                                "vnd.openxmlformats-officedocument."
                                "wordprocessingml.document"
                            ),

                            use_container_width=True,

                            key=(
                                "download_feedback_summary_"
                                + safe_filename(
                                    presenter_name
                                )
                            )
                        )


                    # =========================================
                    # DOWNLOAD ZIP
                    # =========================================

                    if len(reports) > 1:

                        st.download_button(
                            "📦 Download All Presenter Summaries",
                            data=(
                                st.session_state[
                                    "feedback_summary_zip"
                                ]
                            ),
                            file_name=(
                                "Presenter_Teaching_"
                                "Evaluation_Summaries.zip"
                            ),
                            mime="application/zip",
                            use_container_width=True,
                            key=(
                                "download_all_"
                                "feedback_summaries"
                            )
                        )



