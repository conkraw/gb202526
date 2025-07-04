import re
import streamlit as st
import pandas as pd

st.set_page_config(page_title="OASIS Eval Formatter")
st.title("🔄 OASIS Evaluation Formatter")

# 1) Upload
uploaded = st.file_uploader("Upload your raw CSV", type="csv")
if not uploaded:
    st.stop()

# 2) Read as strings
df = pd.read_csv(uploaded, dtype=str)

# 3) QUICK HEADER‐CLEANING: "Course ID" → "course_id", "1 Question Number" → "q1_question_number", etc.
def rename_col(col: str) -> str:
    col = col.strip()
    # detect leading question number
    m = re.match(r"^(\d+)\s+(.+)$", col)
    if m:
        num, rest = m.groups()
        rest = rest.lower().replace(" ", "_")
        return f"q{num}_{rest}"
    return col.lower().replace(" ", "_")

df.columns = [rename_col(c) for c in df.columns]

# 4) Build your master list  
front = [
    "record_id","course_id","department","course","location",
    "start_date","end_date","course_type","student","student_username",
    "student_external_id","student_designation","student_email",
    "student_aamc_id","student_usmle_id","student_gender","student_level",
    "student_default_classification","evaluator","evaluator_username",
    "evaluator_external_id","evaluator_email","evaluator_gender",
    "who_completed","evaluation","form_record","submit_date"
]

q_suffixes = [
    "question_number","question_id","question","answer_text",
    "multiple_choice_order","multiple_choice_value","multiple_choice_label"
]
questions = [f"q{i}_{s}" for i in range(1,24) for s in q_suffixes]

tail = ["oasis_eval_complete","test_complete"]

master_cols = front + questions + tail

# 5) Reorder to exactly your master list (will KeyError if any name is still missing—
#    you can st.write(set(master_cols)-set(df.columns)) to debug)
df = df.reindex(columns=master_cols)

# 6) Inject REDCap fields
df["record_id"]               = df["student_external_id"]
df["redcap_repeat_instrument"] = "oasis_eval"
df["redcap_repeat_instance"]   = df.groupby("record_id").cumcount() + 1

# 7) Move the three key REDCap fields to the front
final_order = [
  "record_id","redcap_repeat_instrument","redcap_repeat_instance"
] + master_cols
df = df.reindex(columns=final_order)

# 8) Show preview
st.dataframe(df, height=400)

# 9) Download button
csv = df.to_csv(index=False).encode("utf-8")
st.download_button(
    "📥 Download formatted CSV",
    data=csv,
    file_name="oasis_eval_formatted.csv",
    mime="text/csv",
)
