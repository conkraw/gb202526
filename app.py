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

# choose which instrument you want to format
instrument = st.sidebar.selectbox(
    "Select instrument", 
    ["OASIS Evaluation", "Checklist Entry", "Email Record Mapper", "NBME Scores", "Preceptor Matching", "Roster", "Weekly Quiz Reports"]
)

if instrument == "OASIS Evaluation":
    st.header("📋 OASIS Evaluation Formatter")
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
                      
    st.dataframe(df, height=400)
    st.download_button(
        "📥 Download formatted OASIS CSV",
        df.to_csv(index=False).encode("utf-8"),
        file_name="oasis_eval_formatted.csv",
        mime="text/csv",
    )


elif instrument == "Checklist Entry":
    st.header("🔖 Checklist Entry Merger")
    uploaded = st.file_uploader(
        "Upload exactly two checklist CSVs",
        type="csv",
        accept_multiple_files=True,
        key="clist"
    )
    if not uploaded:
        st.stop()
    if len(uploaded) != 2:
        st.warning("Please upload *exactly* two CSV files here.")
        st.stop()

    # read + concat
    dfs = [pd.read_csv(f, dtype=str) for f in uploaded]
    df_cl = pd.concat(dfs, ignore_index=True, sort=False)

    # rename only your 22 columns
    rename_map = {
        "Student name":           "student_name",
        "External ID":            "external_id",
        "Email":                  "email",
        "Start Date":             "start_date_cl",
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

    # select + reorder
    target = list(rename_map.values())
    df_cl = df_cl[target]

    # move external_id → record_id up front
    df_cl = df_cl.rename(columns={"external_id": "record_id"})
    cols = ["record_id"] + [c for c in df_cl.columns if c != "record_id"]
    df_cl = df_cl[cols]

    # add REDCap repeater
    df_cl["redcap_repeat_instrument"] = "checklist_entry"
    df_cl["redcap_repeat_instance"]   = df_cl.groupby("record_id").cumcount() + 1

    # final order
    all_cols = df_cl.columns.tolist()
    # ensure instrument + instance are last
    all_cols = [c for c in all_cols if c not in ("redcap_repeat_instrument","redcap_repeat_instance")]
    all_cols += ["redcap_repeat_instrument","redcap_repeat_instance"]
    df_cl = df_cl[all_cols]

    df_cl = df_cl.drop(columns=["email","date"])
    
    st.dataframe(df_cl, height=400)
    st.download_button(
        "📥 Download formatted checklist CSV",
        df_cl.to_csv(index=False).encode("utf-8"),
        file_name="checklist_entries.csv",
        mime="text/csv",
    )

# ─── NBME Score ─────────────────────────────────────────────────────────────

elif instrument == "NBME Scores":
    st.header("🔖 NBME")

    # upload exactly one Excel file
    nbme_file = st.file_uploader(
        "Upload exactly one NBME XLSX",
        type=["xlsx"],
        accept_multiple_files=False,
        key="nbme"
    )
    if not nbme_file:
        st.stop()

    # read the specific worksheet
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
    df_nbme = df_nbme.rename(columns=rename_map_nbme)

    # keep only those nine columns, in that order
    df_nbme = df_nbme[list(rename_map_nbme.values())]

    # move external_id → record_id up front
    df_nbme = df_nbme.rename(columns={"external_id": "record_id"})
    cols = ["record_id"] + [c for c in df_nbme.columns if c != "record_id"]
    df_nbme = df_nbme[cols]
    
    # add REDCap repeater
    df_nbme["redcap_repeat_instrument"] = "oasis_eval"
    df_nbme["redcap_repeat_instance"]   = df_nbme.groupby("record_id").cumcount() + 1
    
    # preview + download
    st.dataframe(df_nbme, height=400)
    st.download_button(
        "📥 Download formatted NBME XLSX → CSV",
        df_nbme.to_csv(index=False).encode("utf-8"),
        file_name="nbme_scores_formatted.csv",
        mime="text/csv",
    )

elif instrument == "Preceptor Matching":
    st.header("🔖 Preceptor Matching")

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
        "Student Activity":              "student_activity",
        "Manual Evaluations":            "manual_evaluations",
    }
    df_pmx = df_pmx.rename(columns=rename_map)

    # keep only those columns, in that exact order
    df_pmx = df_pmx[list(rename_map.values())]

    # move record_id to front
    df_pmx = df_pmx[["record_id"] + [c for c in df_pmx.columns if c != "record_id"]]

    # add REDCap repeater fields
    df_pmx["redcap_repeat_instrument"] = "oasis_eval"
    df_pmx["redcap_repeat_instance"]   = df_pmx.groupby("record_id").cumcount() + 1

    df_pmx = df_pmx.drop(columns=["start_date","end_date","location","student_name","student_username","student_email"])

    # ─── normalize manual_evaluations to one per row ────────────────────
    # split on "|" into lists
    df_pmx["manual_evaluations"] = df_pmx["manual_evaluations"] \
        .fillna("") \
        .str.split("|")
    
    # explode so each list element gets its own row
    df_pmx = df_pmx.explode("manual_evaluations")
    
    # remove leading "*" and any extra whitespace
    df_pmx["manual_evaluations"] = df_pmx["manual_evaluations"] \
        .str.lstrip("*") \
        .str.strip()

        # ─── drop unwanted categories ───────────────────────────────────────
    to_drop = ["Clinical Teaching Eval", "Mid-Cycle Feedback"]
    df_pmx = df_pmx[~df_pmx["manual_evaluations"].isin(to_drop)]

    # get all unique manual_evaluations values
    opts = df_pmx["manual_evaluations"].dropna().unique().tolist()
    
    # multiselect defaulting to all, so you can deselect any you don’t want
    selected = st.multiselect(
        "Filter by manual_evaluations:",
        options=opts,
        default=opts
    )
    
    # filter the DataFrame to only those values
    df_pmx = df_pmx[df_pmx["manual_evaluations"].isin(selected)]


    # preview + download
    st.dataframe(df_pmx, height=400)
    st.download_button(
        "📥 Download formatted Preceptor Matching CSV",
        df_pmx.to_csv(index=False).encode("utf-8"),
        file_name="preceptor_matching_formatted.csv",
        mime="text/csv",
    )

elif instrument == "Email Record Mapper":
    st.header("📧 Email Record Mapper")

    # Upload exactly one Roster CSV
    roster_file = st.file_uploader(
        "Upload a Roster CSV",
        type=["csv"],
        accept_multiple_files=False,
        key="roster_upload"
    )
    if not roster_file:
        st.stop()

    # Read the CSV
    df_roster = pd.read_csv(roster_file, dtype=str)

    # Rename only the needed columns
    rename_map = {
        "Email Address": "email",
        "External ID": "record_id",
    }
    df_roster = df_roster.rename(columns=rename_map)

    # Keep only relevant columns (you can customize this list)
    keep_cols = ["record_id", "email"]
    df_roster = df_roster[keep_cols]

    # Remove rows with missing emails or record_id
    df_roster = df_roster.dropna(subset=["record_id", "email"])

    # Optional: Sort by student_name or record_id
    df_roster = df_roster.sort_values(by="email")

    # Preview and download
    st.dataframe(df_roster, height=400)
    # Create a Word doc in memory
    doc = Document()
    doc.add_heading('REDCap Dropdown: record_id, email', level=1)
    
    # Add each line as plain text
    for _, row in df_roster.iterrows():
        record_id = str(row['record_id']).strip()
        email = str(row['email']).strip()
        doc.add_paragraph(f"{record_id}, {email}")
    
    # Save to BytesIO
    doc_io = BytesIO()
    doc.save(doc_io)
    doc_io.seek(0)

    st.download_button(
        label="📥 Download REDCap Dropdown (Word)",
        data=doc_io,
        file_name="email_roster_dropdown.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

elif instrument == "Weekly Quiz Reports":
    st.header("🔖 Weekly Quiz Reports")

    # 1) upload exactly four CSVs
    uploaded = st.file_uploader(
        "Upload exactly four Weekly Quiz CSVs",
        type=["csv"],
        accept_multiple_files=True,
        key="weekly_quiz"
    )
    if not uploaded:
        st.stop()
    if len(uploaded) != 4:
        st.warning("Please upload *exactly* four CSV files here.")
        st.stop()

    # 2) read + concat
    dfs = [pd.read_csv(f, dtype=str) for f in uploaded]
    df_quiz = pd.concat(dfs, ignore_index=True, sort=False)

    # 3) Clean the sis_id and create record_id
    df_quiz["record_id"] = df_quiz["sis_id"].str.replace(r"@psu\.edu", "", regex=True)

    # 4) rename only the columns you want to send to REDCap
    rename_map_quiz = {
        "name":            "student_name",
        "record_id":       "record_id",  # already cleaned
        "submitted":       "submitted_date",
        "attempt":         "attempt_number",
        "n correct":       "num_correct",
        "n incorrect":     "num_incorrect",
        "score":           "quiz_score",
        "quiz_1_late":     "quiz_1_late",
        "quiz_2_late":     "quiz_2_late",
        "quiz_3_late":     "quiz_3_late",
        "quiz_4_late":     "quiz_4_late",
        # … add other necessary mappings here …
    }
    df_quiz = df_quiz.rename(columns=rename_map_quiz)

    # 5) Select + reorder to exactly those fields
    df_quiz = df_quiz[list(rename_map_quiz.values())]

    # 6) Remove student_name, attempt_number, num_correct, num_incorrect
    df_quiz.drop(columns=["student_name", "attempt_number", "num_correct", "num_incorrect"], inplace=True)

    # 7) Calculate quiz score percentage (divide by 20 and multiply by 100)
    df_quiz["quiz_score"] = pd.to_numeric(df_quiz["quiz_score"], errors='coerce')
    df_quiz["quiz_score"] = (df_quiz["quiz_score"] / 20) * 100

    # 8) Handle missing scores (if no score exists, leave blank)
    df_quiz["quiz_score"] = df_quiz["quiz_score"].fillna('')

    # 9) Handle repeated quizzes: take the latest score
    df_quiz = df_quiz.sort_values(by=["record_id", "submitted_date"], ascending=[True, False])  # Sort by record_id and most recent date
    df_quiz = df_quiz.drop_duplicates(subset=["record_id"], keep="first")  # Keep the latest score per student

    # 10) Renaming the quiz columns
    df_quiz["quiz1"] = df_quiz["quiz_score"]  # You can adapt this to quiz1, quiz2, etc. based on your dataset logic
    
    # 11) Handle quiz late dates (convert from UTC to US/Eastern and set to 23:59)
    quiz_late_columns = ["quiz_1_late", "quiz_2_late", "quiz_3_late", "quiz_4_late"]

    # Loop through each quiz late column and handle conversion
    for col in quiz_late_columns:
        # Convert to datetime if necessary
        df_quiz[col] = pd.to_datetime(df_quiz[col], errors='coerce')  # handle invalid dates if any

        # Convert to UTC if naive and then convert to US/Eastern
        if df_quiz[col].dt.tz is None:
            df_quiz[col] = df_quiz[col].dt.tz_localize('UTC').dt.tz_convert('US/Eastern')
        else:
            df_quiz[col] = df_quiz[col].dt.tz_convert('US/Eastern')
        
        # Set time to 23:59 (no seconds)
        df_quiz[col] = df_quiz[col].dt.normalize() + pd.Timedelta(hours=23, minutes=59)


    # 14) Preview + download
    st.dataframe(df_quiz, height=400)
    st.download_button(
        "📥 Download formatted Weekly Quiz CSV",
        df_quiz.to_csv(index=False).encode("utf-8"),
        file_name="weekly_quiz_formatted.csv",
        mime="text/csv",
    )


elif instrument == "Roster":
    st.header("🔖 Roster")

    # upload exactly one CSV
    roster_file = st.file_uploader(
        "Upload exactly one Roster CSV",
        type=["csv"],
        accept_multiple_files=False,
        key="roster"
    )
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
    df_roster["start_date"] = pd.to_datetime(df_roster["start_date"], infer_datetime_format=True)
    
    # 1) grab each unique date, sorted oldest → newest
    unique_dates = sorted(df_roster["start_date"].dropna().unique())
    
    # 2) for each one, make a new column rot_date_#
    for idx, dt in enumerate(unique_dates, 1):
        df_roster[f"rot_date_{idx}"] = dt.strftime("%Y-%m-%d")
    
    # 3) build a mapping from date → rotation code
    rotation_map = {dt: f"R{idx}" for idx, dt in enumerate(unique_dates, 1)}
    
    # 4) assign each student’s rotation1 based on their start_date
    df_roster["rotation1"] = df_roster["start_date"].map(rotation_map)

    df_roster["rotation"] = df_roster["start_date"].map(rotation_map)

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
    df_roster["ass_middue_date"]   = df_roster["quiz_due_2"]
    df_roster["ass_due_date"]      = df_roster["quiz_due_4"]
    df_roster["docass_due_date_1"] = df_roster["quiz_due_2"]
    df_roster["docass_due_date_2"] = df_roster["quiz_due_4"]
    
    # ─── 5) Grade due date: 6 weeks after end_date ──────────────────────────────
    df_roster["grade_due_date"] = df_roster["end_date"] + pd.Timedelta(weeks=6)

    # ─── 6) Normalize all due dates to 23:59 with no seconds ─────────────────
    due_cols = [
        "quiz_due_1","quiz_due_2","quiz_due_3","quiz_due_4",
        "ass_middue_date","ass_due_date",
        "docass_due_date_1","docass_due_date_2",
        "grade_due_date"
    ]
    
    for col in due_cols:
        #df_roster[col] = (df_roster[col].dt.normalize() + pd.Timedelta(hours=23, minutes=59)).dt.strftime("%Y-%m-%d %H:%M")
        #df_roster[col] = (df_roster[col].dt.normalize() + pd.Timedelta(hours=23, minutes=59)).dt.strftime("%m/%d/%Y 23:59")
        df_roster[col] = (df_roster[col].dt.normalize() + pd.Timedelta(hours=23, minutes=59)).dt.strftime("%-m/%-d/%Y 23:59")

    # preview + download
    st.dataframe(df_roster, height=400)
    
    st.download_button("📥 Download formatted Roster CSV",df_roster.to_csv(index=False).encode("utf-8"),file_name="roster_formatted.csv",mime="text/csv")



