import re
import streamlit as st
import pandas as pd

st.set_page_config(page_title="REDCap Formatter", layout="wide")
st.title("🔄 REDCap Instruments Formatter")

# choose which instrument you want to format
instrument = st.sidebar.selectbox(
    "Select instrument", 
    ["OASIS Evaluation", "Checklist Entry", "NBME Scores", "Preceptor Matching"]
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
    df = df.drop(columns=["student","location"]) #Cannot have these columns in the repeating instrument. 
                      
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

