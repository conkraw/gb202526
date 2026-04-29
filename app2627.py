import re
import streamlit as st
import pandas as pd
from io import BytesIO
from docx import Document
import pytz
import pandas as pd
import streamlit as st

st.set_page_config(page_title="REDCap Formatter", layout="wide")
st.title("🔄 REDCap Instruments Formatter")
st.markdown("[Open REDCap Data Import](https://redcap.ctsi.psu.edu/redcap_v15.5.35/index.php?pid=19389&route=DataImportController:index)")


# choose which instrument you want to format
instrument = st.sidebar.selectbox("Select instrument", ["OASIS Evaluation", "Checklist Entry", "Preceptor Matching", "NBME Scores", "Roster_HMC", "Roster_KP", "Roster_Updater"])

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
    st.header("🔖 Roster KP")
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
    rotation_map = {dt: f"r{idx}" for idx, dt in enumerate(unique_dates, 1)}
    
    # 4) assign each student’s rotation1 based on their start_date
    df_roster["rotation1"] = "KPLIC"

    df_roster["rotation"] = "KPLIC"

    # 3) now drop your old columns
    df_roster.drop(columns=renamed_cols, errors="ignore", inplace=True)

    #DUE DATES
    
    # ─── 1) Ensure start_date and end_date are datetime ─────────────────────────
    df_roster["start_date"] = pd.to_datetime(df_roster["start_date"], infer_datetime_format=True)
    df_roster["end_date"]   = pd.to_datetime(df_roster["end_date"], infer_datetime_format=True)
    
    # ─── 2) Compute first Sunday on/after start_date ────────────────────────────
    days_to_sunday = (6 - df_roster["start_date"].dt.weekday) % 7
    first_sunday   = df_roster["start_date"] + pd.to_timedelta(days_to_sunday, unit="D")
    
    # ─── 3) Create quiz_due_1 … quiz_due_4 ──────────────────────────────────────
    for n in range(1, 5):
        df_roster[f"quiz_due_{n}"] = first_sunday + pd.Timedelta(weeks=(n - 1))
    
    # ─── 4) Alias assignment & doc-assignment due dates ─────────────────────────
    df_roster["ass_due_date"]      = df_roster["quiz_due_4"]

    # ─── 5) Grade due date: 6 weeks after end_date ──────────────────────────────
    df_roster["grade_due_date"] = df_roster["end_date"] + pd.Timedelta(weeks=6)

    # ─── 6) Normalize all due dates to 23:59 with no seconds ─────────────────
    due_cols = ["ass_due_date","grade_due_date"]
    
    for col in due_cols:
        df_roster[col] = (df_roster[col].dt.normalize() + pd.Timedelta(hours=23, minutes=59)).dt.strftime("%m-%d-%Y 23:59")

    df_roster["start_date"] = df_roster["start_date"].dt.strftime("%m-%d-%Y")
    df_roster["end_date"] = df_roster["end_date"].dt.strftime("%m-%d-%Y")
    
    # preview + download

    # --------- REMOVE QUIZ DUE COLUMNS COMPLETELY ----------
    df_roster = df_roster.drop(columns=[c for c in df_roster.columns if c.startswith("quiz_due_") or c.startswith("rot_date")],errors="ignore")

    st.dataframe(df_roster, height=400)

    st.download_button("📥 Download formatted Roster CSV",df_roster.to_csv(index=False).encode("utf-8"),file_name="roster_formatted.csv",mime="text/csv")

elif instrument == "Roster_KP":
    st.header("🔖 Roster KP")
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
    rotation_map = {dt: f"r{idx}" for idx, dt in enumerate(unique_dates, 1)}
    
    # 4) assign each student’s rotation1 based on their start_date
    df_roster["rotation1"] = "KPLIC"

    df_roster["rotation"] = "KPLIC"

    # 3) now drop your old columns
    df_roster.drop(columns=renamed_cols, errors="ignore", inplace=True)

    #DUE DATES
    
    # ─── 1) Ensure start_date and end_date are datetime ─────────────────────────
    df_roster["start_date"] = pd.to_datetime(df_roster["start_date"], infer_datetime_format=True)
    df_roster["end_date"]   = pd.to_datetime(df_roster["end_date"], infer_datetime_format=True)
    
    # ─── 2) Compute first Sunday on/after start_date ────────────────────────────
    days_to_sunday = (6 - df_roster["start_date"].dt.weekday) % 7
    first_sunday   = df_roster["start_date"] + pd.to_timedelta(days_to_sunday, unit="D")
    
    # ─── 3) Create quiz_due_1 … quiz_due_4 ──────────────────────────────────────
    for n in range(1, 5):
        df_roster[f"quiz_due_{n}"] = first_sunday + pd.Timedelta(weeks=(n - 1))
    
    # ─── 4) Alias assignment & doc-assignment due dates ─────────────────────────
    df_roster["ass_due_date"]      = df_roster["quiz_due_4"]

    # ─── 5) Grade due date: 6 weeks after end_date ──────────────────────────────
    df_roster["grade_due_date"] = df_roster["end_date"] + pd.Timedelta(weeks=6)

    # ─── 6) Normalize all due dates to 23:59 with no seconds ─────────────────
    due_cols = ["ass_due_date","grade_due_date"]
    
    for col in due_cols:
        df_roster[col] = (df_roster[col].dt.normalize() + pd.Timedelta(hours=23, minutes=59)).dt.strftime("%m-%d-%Y 23:59")

    df_roster["start_date"] = df_roster["start_date"].dt.strftime("%m-%d-%Y")
    df_roster["end_date"] = df_roster["end_date"].dt.strftime("%m-%d-%Y")
    
    # preview + download

    # --------- REMOVE QUIZ DUE COLUMNS COMPLETELY ----------
    df_roster = df_roster.drop(columns=[c for c in df_roster.columns if c.startswith("quiz_due_") or c.startswith("rot_date")],errors="ignore")

    st.dataframe(df_roster, height=400)

    st.download_button("📥 Download formatted Roster CSV",df_roster.to_csv(index=False).encode("utf-8"),file_name="roster_formatted.csv",mime="text/csv")

elif instrument == "Roster_Updater":
    st.header("🔖 Roster Updater")
    st.markdown("[🔗 Roster Website](https://oasis.pennstatehealth.net/admin/course/roster/)")

    import pandas as pd

    old_file = st.file_uploader(
        "Upload OLD Roster CSV",
        type=["csv"],
        accept_multiple_files=False,
        key="old_roster"
    )

    new_file = st.file_uploader(
        "Upload NEW Roster CSV",
        type=["csv"],
        accept_multiple_files=False,
        key="new_roster"
    )

    if not old_file or not new_file:
        st.stop()

    df_old = pd.read_csv(old_file, dtype=str).fillna("")
    df_new_raw = pd.read_csv(new_file, dtype=str).fillna("")

    # Convert OASIS new roster into REDCap-style roster
    df_new = pd.DataFrame()

    df_new["record_id"] = df_new_raw["External ID"].str.strip()
    df_new["legal_name"] = df_new_raw["Student"].str.replace(";", " (", regex=False).str.replace("MD2028", "MD)", regex=False).str.replace("MD2027", "MD)", regex=False)
    df_new["email"] = df_new_raw["Email Address"]
    df_new["psu_id"] = df_new_raw["PSU ID"]
    df_new["track"] = df_new_raw["Track"]
    df_new["location"] = df_new_raw["Location"]

    df_new["start_date"] = pd.to_datetime(df_new_raw["Start Date"]).dt.strftime("%m-%d-%Y")
    df_new["end_date"] = pd.to_datetime(df_new_raw["End Date"]).dt.strftime("%m-%d-%Y")

    df_new["lastname"] = df_new_raw["Student"].str.split(",", expand=True)[0].str.strip()
    df_new["firstname"] = df_new_raw["Student"].str.split(",", expand=True)[1].str.split(";", expand=True)[0].str.strip()
    df_new["name"] = df_new["firstname"] + " " + df_new["lastname"]
    df_new["email_2"] = df_new["record_id"] + "@psu.edu"

    # Assign rotation based on start date order
    rotation_map = {
        "03-16-2026": "r01",
        "04-13-2026": "r02",
        "05-11-2026": "r03",
        "06-08-2026": "r04",
        "07-06-2026": "r05",
        "08-03-2026": "r06",
        "09-01-2026": "r07",
        "09-28-2026": "r08",
        "10-26-2026": "r09",
        "11-23-2026": "r10",
        "01-04-2027": "r11",
        "02-01-2027": "r12",
    }

    df_new["rotation"] = df_new["start_date"].map(rotation_map).fillna("")
    df_new["rotation1"] = df_new["rotation"]

    df_new["ass_due_date"] = (
        pd.to_datetime(df_new["end_date"]) + pd.Timedelta(days=2)
    ).dt.strftime("%m-%d-%Y 23:59")

    df_new["grade_due_date"] = (
        pd.to_datetime(df_new["end_date"]) + pd.Timedelta(days=42)
    ).dt.strftime("%m-%d-%Y 23:59")

    df_new["student_demographics_complete"] = "2"

    # Match OLD file column order exactly
    for col in df_old.columns:
        if col not in df_new.columns:
            df_new[col] = ""

    df_new = df_new[df_old.columns]

    # Clean IDs
    df_old["record_id"] = df_old["record_id"].astype(str).str.strip()
    df_new["record_id"] = df_new["record_id"].astype(str).str.strip()

    # Students removed from new roster
    new_ids = set(df_new["record_id"])
    df_old_only = df_old[~df_old["record_id"].isin(new_ids)].copy()

    # Blank dropped students' active rotation fields
    df_old_only["rotation1"] = ""
    df_old_only["start_date"] = ""

    # Combine clean new roster + retained dropped students
    df_combined = pd.concat([df_new, df_old_only], ignore_index=True)

    df_combined = df_combined.drop_duplicates(
        subset=["record_id"],
        keep="first"
    )

    st.write(f"Rows in NEW file: {len(df_new)}")
    st.write(f"OLD-only rows retained: {len(df_old_only)}")
    st.write(f"Final unique records: {len(df_combined)}")

    st.subheader("Dropped Students")
    st.dataframe(df_old_only)

    st.subheader("Preview of Updated Roster")
    st.dataframe(df_combined)

    csv_output = df_combined.to_csv(index=False).encode("utf-8")

    st.download_button(
        label="Download Updated Roster CSV",
        data=csv_output,
        file_name="updated_roster.csv",
        mime="text/csv"
    )
