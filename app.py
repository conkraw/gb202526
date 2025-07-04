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

# 3) Master column list (in the exact order you provided)
# fixed “front” columns
front = [
    "record_id","course_id","department","course","location",
    "start_date","end_date","course_type","student","student_username",
    "student_external_id","student_designation","student_email",
    "student_aamc_id","student_usmle_id","student_gender","student_level",
    "student_default_classification","evaluator","evaluator_username",
    "evaluator_external_id","evaluator_email","evaluator_gender",
    "who_completed","evaluation","form_record","submit_date"
]

# the repeating question‐fields
q_suffixes = [
    "question_number",
    "question_id",
    "question",
    "answer_text",
    "multiple_choice_order",
    "multiple_choice_value",
    "multiple_choice_label",
]

# build q1…q23 automatically
questions = [
    f"q{i}_{sfx}"
    for i in range(1, 24)   # 1 through 23
    for sfx in q_suffixes
]

# the trailing columns
tail = ["oasis_eval_complete", "test_complete"]

# combine into your master list
master_cols = front + questions + tail

df = df[ master_cols ]

# 5) Override record_id with student_external_id
df["record_id"] = df["student_external_id"]

# 6) Add the REDCap repeat fields
df["redcap_repeat_instrument"] = "oasis_eval"
df["redcap_repeat_instance"] = df.groupby("record_id").cumcount() + 1

# 7) Final column order: push our three key fields to the front
front = ["record_id", "redcap_repeat_instrument", "redcap_repeat_instance"]
rest = [c for c in master_cols if c not in front]
df = df[ front + rest ]

# 8) Show preview
st.dataframe(df, height=400)

# 9) Download button
csv = df.to_csv(index=False).encode("utf-8")
st.download_button(
    "📥 Download formatted CSV",
    data=csv,
    file_name="oasis_eval_formatted.csv",
    mime="text/csv"
)
