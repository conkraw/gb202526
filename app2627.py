from __future__ import annotations
import re
import streamlit as st
import pandas as pd
from io import BytesIO
from docx import Document
import pytz
import pandas as pd
import streamlit as st

from urllib.parse import quote_plus

st.set_page_config(page_title="REDCap Formatter", layout="wide")
st.title("🔄 REDCap Instruments Formatter")
st.markdown("[Open REDCap Data Import](https://redcap.ctsi.psu.edu/redcap_v15.5.35/index.php?pid=19389&route=DataImportController:index)")


# choose which instrument you want to format
instrument = st.sidebar.selectbox("Select instrument", ["OASIS Evaluation", "Checklist Entry", "Preceptor Matching", "NBME Scores", "Roster_HMC", "Roster_KP", "Roster_Updater","Oasis Reminder"])

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
    # -----------------------------
    # Defaults
    # -----------------------------
    DEFAULT_EVAL = "Clinical Assessment of Student"
    DEFAULT_REDCAP_BASE = "https://redcap.ctsi.psu.edu/surveys/?s=C7EJ3MPDMCMCFJEP"
    
    
    # -----------------------------
    # General helpers
    # -----------------------------
    def read_csv_any(uploaded_file) -> pd.DataFrame:
        """Read a user-uploaded CSV with a few encoding fallbacks."""
        if uploaded_file is None:
            return pd.DataFrame()
    
        raw = uploaded_file.getvalue()
        last_error = None
    
        for enc in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                return pd.read_csv(BytesIO(raw), dtype=str, encoding=enc).fillna("")
            except Exception as e:
                last_error = e
    
        raise ValueError(f"Could not read CSV. Last error: {last_error}")
    
    
    def normalize_colnames(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df.columns = [str(c).strip().lstrip("\ufeff") for c in df.columns]
        return df
    
    
    def first_existing_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
        for c in candidates:
            if c in df.columns:
                return c
        return None
    
    
    def clean_text(x) -> str:
        return re.sub(r"\s+", " ", str(x or "").strip())
    
    
    def clean_eval_name(x) -> str:
        """Normalize eval names from both files: remove leading asterisks, normalize spacing/case."""
        s = clean_text(x)
        s = s.lstrip("*").strip()
        return re.sub(r"\s+", " ", s).lower()
    
    
    def display_eval_name(x) -> str:
        """Human-facing eval name."""
        s = clean_text(x).lstrip("*").strip()
        return re.sub(r"\s+", " ", s)
    
    
    def clean_email(x) -> str:
        return clean_text(x).lower()
    
    
    def clean_id(x) -> str:
        return clean_text(x).lower()
    
    
    def clean_name_for_display(x) -> str:
        """
        Convert 'Last, First; MD2028' to 'First Last' for readability.
        Leaves already-readable names alone.
        """
        s = clean_text(x)
        s = re.sub(r";\s*MD\d{4}", "", s, flags=re.IGNORECASE).strip()
        if "," in s:
            last, first = s.split(",", 1)
            return f"{first.strip()} {last.strip()}".strip()
        return s
    
    
    def to_date(s: pd.Series) -> pd.Series:
        return pd.to_datetime(s, errors="coerce").dt.normalize()
    
    
    def make_prefill_link(base_url: str, student_name: str, faculty_name: str, partial: bool = False) -> str:
        if not base_url:
            return ""
        url = f"{base_url}&student={quote_plus(str(student_name).strip())}&preceptor={quote_plus(str(faculty_name).strip())}"
        if partial:
            # Your existing shortcut values. Keep/edit as needed.
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
    
    
    # -----------------------------
    # Data preparation
    # -----------------------------
    def prepare_expected_associations(
        assoc_raw: pd.DataFrame,
        selected_eval_key: str,
        as_of_date: pd.Timestamp,
        date_mode: str,
        include_all_students: bool,
    ) -> pd.DataFrame:
        """
        Convert raw evaluation_associations file to one expected-evaluation row per
        student/faculty/evaluation association.
        """
        df = normalize_colnames(assoc_raw)
    
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
        eval_start_col = first_existing_col(df, ["Evaluation Period Start Date", "Start Date"])
        eval_end_col = first_existing_col(df, ["Evaluation Period End Date", "End Date"])
        course_start_col = first_existing_col(df, ["Start Date"])
        course_end_col = first_existing_col(df, ["End Date"])
    
        df["expected_start_date"] = df[eval_start_col] if eval_start_col else ""
        df["expected_end_date"] = df[eval_end_col] if eval_end_col else ""
    
        # If eval dates are blank, fall back row-wise to course dates.
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
        df["evaluation_type"] = df["manual_eval_item"].apply(display_eval_name)
    
        # Drop blanks and common non-reminder categories.
        df = df[df["evaluation_key"].ne("")].copy()
    
        # Keep only the selected eval.
        df = df[df["evaluation_key"].eq(selected_eval_key)].copy()
    
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
            "expected_start",
            "expected_end",
        ]
        return df[keep].drop_duplicates().reset_index(drop=True)
    
    
    def prepare_completed_oasis(oasis_raw: pd.DataFrame, selected_eval_key: str) -> pd.DataFrame:
        """
        Convert raw OASIS question-level export to one row per submitted evaluation.
        """
        df = normalize_colnames(oasis_raw)
    
        # Normalize common OASIS column variants.
        rename = {
            "Answer text": "Answer Text",
            "Multiple Choice Value": "Mult Choice Value",
            "Student External ID": "Student External ID",
            "Evaluator External ID": "Evaluator External ID",
        }
        for old, new in rename.items():
            if old in df.columns and new not in df.columns:
                df = df.rename(columns={old: new})
    
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
        df["evaluation_type"] = df["Evaluation"].apply(display_eval_name)
        df = df[df["evaluation_key"].eq(selected_eval_key)].copy()
    
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
    
        # OASIS is usually question-level. "Form Record" is best if present.
        # If not, the combination below is still one submitted evaluation instance.
        dedupe_cols = [
            "record_id",
            "student_username_key",
            "faculty_username_key",
            "faculty_external_id_key",
            "faculty_email",
            "evaluation_key",
            "submit_dt",
        ]
        if "Form Record" in df.columns:
            dedupe_cols = ["Form Record"]
    
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
            "submit_dt",
            "oasis_start",
            "oasis_end",
        ]
        return df.drop_duplicates(subset=dedupe_cols)[keep].reset_index(drop=True)
    
    
    # -----------------------------
    # Matching logic
    # -----------------------------
    def row_matches(expected_row: pd.Series, completed: pd.DataFrame, allow_email_fallback: bool, allow_username_fallback: bool) -> pd.DataFrame:
        """
        Match expected association to completed OASIS submission.
    
        Important design choice:
        - Do not require date equality. Raw associations may use evaluation-period dates,
          while raw OASIS exports often use course dates.
        - Primary match: student external ID + evaluator external ID + evaluation.
        - Fallbacks: evaluator email and/or evaluator username when external ID is blank.
        """
        c = completed[completed["evaluation_key"].eq(expected_row["evaluation_key"])].copy()
    
        # Student match.
        c = c[c["record_id"].eq(expected_row["record_id"])].copy()
    
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
    
    
    def build_reminder_report(
        expected: pd.DataFrame,
        completed: pd.DataFrame,
        allow_email_fallback: bool,
        allow_username_fallback: bool,
        redcap_base_url: str,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Return:
          reminder_report: Power Automate-ready pending rows
          debug_report: all expected rows with matched count/status
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
                sorted(set([x for x in matches["faculty_name"].astype(str).tolist() if x.strip()]))
            )
            rows.append(row)
    
        debug = pd.DataFrame(rows)
    
        if debug.empty:
            return pd.DataFrame(), debug
    
        # Collapse duplicated expected associations for the same student/faculty/eval.
        group_cols = [
            "record_id",
            "faculty_email",
            "faculty_name",
            "student_name",
            "student_email",
            "evaluation_type",
            "evaluation_key",
        ]
    
        collapsed = (
            debug.groupby(group_cols, dropna=False)
            .agg(
                expected_eval_count=("evaluation_key", "size"),
                completed_eval_count=("completed_eval_count", "max"),
                first_expected_start=("expected_start", "min"),
                last_expected_end=("expected_end", "max"),
                completed_submit_dates=("completed_submit_dates", lambda s: "; ".join(sorted(set("; ".join(s).split("; ")) - {""}))),
                matched_faculty_names=("matched_faculty_names", lambda s: "; ".join(sorted(set("; ".join(s).split("; ")) - {""}))),
            )
            .reset_index()
        )
    
        collapsed["pending_eval_count"] = (
            collapsed["expected_eval_count"] - collapsed["completed_eval_count"]
        ).clip(lower=0)
    
        collapsed["duplicate_match_flag"] = collapsed["expected_eval_count"].apply(lambda n: "YES" if n > 1 else "")
        collapsed["needs_reminder"] = collapsed["pending_eval_count"].apply(lambda n: "YES" if n > 0 else "")
    
        def note(row):
            if row["pending_eval_count"] <= 0:
                return ""
            if row["expected_eval_count"] == 1 and row["completed_eval_count"] == 0:
                return "The student reported working with you, but we have not yet received the corresponding evaluation."
            if row["expected_eval_count"] > 1 and row["completed_eval_count"] == 0:
                return (
                    f"The student reported working with you on {row['expected_eval_count']} occasions, "
                    "but we have not yet received any completed evaluations."
                )
            return (
                f"The student reported working with you on {row['expected_eval_count']} occasions. "
                f"We have received {row['completed_eval_count']} completed evaluation(s) so far and are still missing "
                f"{row['pending_eval_count']}."
            )
    
        collapsed["reminder_note"] = collapsed.apply(note, axis=1)
    
        collapsed["blank_form_link"] = collapsed.apply(
            lambda r: make_prefill_link(redcap_base_url, r["student_name"], r["faculty_name"], partial=False),
            axis=1,
        )
        collapsed["partial_form_link"] = collapsed.apply(
            lambda r: make_prefill_link(redcap_base_url, r["student_name"], r["faculty_name"], partial=True),
            axis=1,
        )
    
        reminders = collapsed[collapsed["needs_reminder"].eq("YES")].copy()
    
        final_cols = [
            "faculty_email",
            "faculty_name",
            "student_name",
            "student_email",
            "evaluation_type",
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
    
        # Power Automate cleanup.
        for col in reminders.columns:
            reminders[col] = reminders[col].apply(safe_for_power_automate)
    
        return reminders.reset_index(drop=True), collapsed.reset_index(drop=True)
    
    
    # -----------------------------
    # Streamlit UI
    # -----------------------------
    st.set_page_config(
        page_title="OASIS Preceptor Reminder Builder",
        page_icon="📋",
        layout="wide",
    )
    
    st.title("📋 OASIS Preceptor Evaluation Reminder Builder")
    st.write(
        "Upload the raw OASIS evaluation export and the raw evaluation associations/preceptor matching file. "
        "The app will cross-reference expected evaluations against submitted evaluations and generate a "
        "Power Automate-ready reminder CSV."
    )
    
    with st.sidebar:
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
    
        st.header("Reminder settings")
        eval_name = st.text_input("Evaluation to track", value=DEFAULT_EVAL)
        selected_eval_key = clean_eval_name(eval_name)
    
        as_of_date = pd.to_datetime(
            st.date_input("As-of date", value=pd.Timestamp.today().date())
        ).normalize()
    
        date_mode = st.selectbox(
            "Which associations should be considered?",
            [
                "Active as of selected date",
                "Evaluation period ended on/before selected date",
                "No date filter",
            ],
            index=0,
        )
    
        include_all_students = st.checkbox("Include 'All Students' rows", value=False)
        allow_email_fallback = st.checkbox("Allow evaluator email fallback", value=True)
        allow_username_fallback = st.checkbox("Allow evaluator username fallback", value=True)
    
        st.header("Optional REDCap link")
        redcap_base_url = st.text_input("REDCap survey base URL", value=DEFAULT_REDCAP_BASE)
    
    run_clicked = st.button("Build reminder CSV", type="primary")
    
    if not run_clicked:
        st.info("Upload both CSV files, adjust the settings, then click **Build reminder CSV**.")
        st.stop()
    
    if assoc_file is None or oasis_file is None:
        st.error("Please upload both the raw association file and the raw OASIS evaluation export.")
        st.stop()
    
    try:
        assoc_raw = read_csv_any(assoc_file)
        oasis_raw = read_csv_any(oasis_file)
    
        expected = prepare_expected_associations(
            assoc_raw=assoc_raw,
            selected_eval_key=selected_eval_key,
            as_of_date=as_of_date,
            date_mode=date_mode,
            include_all_students=include_all_students,
        )
    
        completed = prepare_completed_oasis(
            oasis_raw=oasis_raw,
            selected_eval_key=selected_eval_key,
        )
    
        reminders, debug = build_reminder_report(
            expected=expected,
            completed=completed,
            allow_email_fallback=allow_email_fallback,
            allow_username_fallback=allow_username_fallback,
            redcap_base_url=redcap_base_url,
        )
    
    except Exception as e:
        st.exception(e)
        st.stop()
    
    # -----------------------------
    # Results
    # -----------------------------
    st.success("Done.")
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Expected associations considered", len(expected))
    m2.metric("Submitted evaluations found", len(completed))
    m3.metric("Reminder rows", len(reminders))
    
    tab1, tab2, tab3 = st.tabs(["Power Automate CSV", "Matched / debug view", "Raw normalized inputs"])
    
    with tab1:
        st.subheader("Power Automate-ready reminder file")
        st.dataframe(reminders, use_container_width=True)
    
        csv_bytes = reminders.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="Download preceptor_eval_reminders.csv",
            data=csv_bytes,
            file_name="preceptor_eval_reminders.csv",
            mime="text/csv",
        )
    
    with tab2:
        st.subheader("All expected rows after matching")
        st.write(
            "Rows with `pending_eval_count = 0` were matched to a submitted OASIS evaluation. "
            "This tab is the best place to troubleshoot cases like Kaelor/Madeline."
        )
        st.dataframe(debug, use_container_width=True)
    
        debug_bytes = debug.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="Download debug_match_report.csv",
            data=debug_bytes,
            file_name="debug_match_report.csv",
            mime="text/csv",
        )
    
    with tab3:
        st.subheader("Normalized expected associations")
        st.dataframe(expected, use_container_width=True)
    
        st.subheader("Normalized completed OASIS submissions")
        st.dataframe(completed, use_container_width=True)

    
