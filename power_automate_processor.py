# ==============================
# IMPORTS
# ==============================
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import quote_plus

# ==============================
# SETTINGS
# ==============================
DELETE_REMINDER_HISTORY = "YES"   # "YES" = force delete history file

DEFAULT_EMAIL = "ckrawiec@pennstatehealth.psu.edu"
MATCH_EVAL_FILTER = "Clinical Assessment of Student"
EVAL_NAME_FILTER = "Clinical Assessment of Student"

REDCAP_BASE = "https://redcap.ctsi.psu.edu/surveys/?s=C7EJ3MPDMCMCFJEP"


# ==============================
# PATHS
# ==============================
RAW_MATCH_PATH = Path(r"C:\Users\ckrawiec\OneDrive - Penn State Health\PEDIATRICCLERKSHIPGR-PreceptorMatching_DATA_2026-03-09_0829.csv")
RAW_EVAL_PATH = Path(r"C:\Users\ckrawiec\OneDrive - Penn State Health\PEDIATRICCLERKSHIPGR-OasisEvaluation_DATA_2026-03-09_0829.csv")

MATCH_PATH = Path(r"C:\Users\ckrawiec\OneDrive - Penn State Health\preceptor_match_review.csv")
EVAL_PATH = Path(r"C:\Users\ckrawiec\OneDrive - Penn State Health\oasis_evaluation_submission.csv")
HISTORY_PATH = Path(r"C:\Users\ckrawiec\OneDrive - Penn State Health\preceptor_reminder_history.csv")

OUT_REMINDER_REPORT = Path(r"C:\Users\ckrawiec\OneDrive - Penn State Health\CLERKSHIP_REMINDER_FOLDER\preceptor_eval_reminders.csv")

# ==============================
# DATE
# ==============================  
GRACE_DAYS = 0
MANUAL_DATE = None  # <-- set like "2026-04-01" when you want override
#MANUAL_DATE = "2026-06-08"  # <-- set like "2026-04-01" when you want override

# ==============================
# PATHS - Delete
# ==============================

#BASE_DIR = Path(".")

#RAW_MATCH_PATH = BASE_DIR / "PEDIATRICCLERKSHIPGR-PreceptorMatching_DATA_2026-03-09_0829.csv"
#RAW_EVAL_PATH = BASE_DIR / "PEDIATRICCLERKSHIPGR-OasisEvaluation_DATA_2026-03-09_0829.csv"

#MATCH_PATH = BASE_DIR / "preceptor_match_review.csv"
#EVAL_PATH = BASE_DIR / "oasis_evaluation_submission.csv"
#HISTORY_PATH = BASE_DIR / "preceptor_reminder_history.csv"

#OUT_REMINDER_REPORT = BASE_DIR / "CLERKSHIP_REMINDER_FOLDER" / "preceptor_eval_reminders.csv"

#OUT_REMINDER_REPORT = "preceptor_eval_reminders.csv"

# ==============================
# FUNCTIONS
# ==============================
def get_today(manual_date=None):
    if manual_date:
        return datetime.strptime(manual_date, "%Y-%m-%d")
    return datetime.today()


def delete_preceptor_history(history_path):
    if history_path.exists():
        history_path.unlink()
        print(f"Deleted: {history_path.name}")
    else:
        print(f"File not found: {history_path.name}")


def delete_history_if_24_days_from_start(raw_eval_path, history_path, manual_date=None):
    today = get_today(manual_date)

    df_eval = pd.read_csv(raw_eval_path, dtype=str)

    if "start_date" in df_eval.columns:
        date_col = "start_date"
    elif "Start Date" in df_eval.columns:
        date_col = "Start Date"
    else:
        print("No start_date column found in raw evaluation file")
        return

    df_eval[date_col] = pd.to_datetime(df_eval[date_col], errors="coerce")
    df_eval = df_eval.dropna(subset=[date_col])

    if df_eval.empty:
        print("No valid start dates found")
        return

    cutoff_dates = df_eval[date_col] + timedelta(days=24)

    if (today >= cutoff_dates).any():
        print("24-day threshold reached. Deleting history file.")
        delete_preceptor_history(history_path)
    else:
        print("No start date has reached 24 days yet. Keeping history file.")


# ==============================
# REMINDER HISTORY LOGIC
# ==============================
if DELETE_REMINDER_HISTORY.upper() == "YES":
    print("Manual override enabled.")
    delete_preceptor_history(HISTORY_PATH)
else:
    delete_history_if_24_days_from_start(
        RAW_EVAL_PATH,
        HISTORY_PATH,
        MANUAL_DATE
    )

# ==============================
# CAS PRECEPTOR REMINDER
# ==============================

# ==============================
# HELPERS
# ==============================
def normalize_email(s):
    return str(s).strip().lower()

def normalize_eval_name(s):
    return str(s).strip().lstrip("*").strip()

def clean_name(s):
    s = str(s).strip()
    if "," in s:
        last, first = s.split(",", 1)
        return f"{first.strip()} {last.strip()}"
    return s

def make_prefill_link(student_name, faculty_name, partial=False):
    student = quote_plus(str(student_name).strip())
    preceptor = quote_plus(str(faculty_name).strip())

    url = f"{REDCAP_BASE}&student={student}&preceptor={preceptor}"

    if partial:
        url += "&complete=1&ph=3&ch=3&pp=3&cp=3"

    return url

def load_history(history_path):
    history_file = Path(history_path)

    if not history_file.exists():
        return pd.DataFrame(columns=["record_id", "faculty_email", "evaluation_type"])

    try:
        hist = pd.read_csv(history_path, dtype=str).fillna("")
    except Exception as e:
        print(f"Could not read history file: {e}")
        return pd.DataFrame(columns=["record_id", "faculty_email", "evaluation_type"])

    for col in ["record_id", "faculty_email", "evaluation_type"]:
        if col not in hist.columns:
            hist[col] = ""

    hist["record_id"] = hist["record_id"].astype(str).str.strip()
    hist["faculty_email"] = hist["faculty_email"].apply(normalize_email)
    hist["evaluation_type"] = hist["evaluation_type"].astype(str).str.strip()

    return hist[["record_id", "faculty_email", "evaluation_type"]].drop_duplicates().reset_index(drop=True)

def remove_already_reminded(current_report, history_df):
    if current_report.empty:
        return current_report

    current_report = current_report.copy()
    current_report["record_id"] = current_report["record_id"].astype(str).str.strip()
    current_report["faculty_email_norm"] = current_report["faculty_email"].apply(normalize_email)
    current_report["evaluation_type"] = current_report["evaluation_type"].astype(str).str.strip()

    history_keys = set(
        zip(
            history_df["record_id"],
            history_df["faculty_email"],
            history_df["evaluation_type"]
        )
    )

    before = len(current_report)

    current_report = current_report[
        ~current_report.apply(
            lambda row: (
                row["record_id"],
                row["faculty_email_norm"],
                row["evaluation_type"]
            ) in history_keys,
            axis=1
        )
    ].copy()

    after = len(current_report)
    print(f"Removed {before - after} reminder(s) already found in history.")

    return current_report.drop(columns=["faculty_email_norm"], errors="ignore")

def update_history(history_path, reminders_sent_df):
    history_file = Path(history_path)

    if reminders_sent_df.empty:
        if not history_file.exists():
            pd.DataFrame(columns=["record_id", "faculty_email", "evaluation_type"]).to_csv(history_file, index=False)
        return

    new_hist = reminders_sent_df[["record_id", "faculty_email", "evaluation_type"]].copy()
    new_hist["record_id"] = new_hist["record_id"].astype(str).str.strip()
    new_hist["faculty_email"] = new_hist["faculty_email"].apply(normalize_email)
    new_hist["evaluation_type"] = new_hist["evaluation_type"].astype(str).str.strip()
    new_hist = new_hist.drop_duplicates()

    old_hist = load_history(history_path)

    combined = pd.concat([old_hist, new_hist], ignore_index=True)
    combined = combined.drop_duplicates().sort_values(
        ["record_id", "faculty_email", "evaluation_type"]
    ).reset_index(drop=True)

    combined.to_csv(history_file, index=False)
    print(f"Updated history file: {history_path}")

# ==============================
# STEP 1: BUILD SIMPLIFIED FILES
# ==============================
def build_simplified_file(
    input_path,
    output_path,
    keep_cols,
    rename_map=None,
    eval_filter=None
):
    df = pd.read_csv(input_path, dtype=str).fillna("")
    df = df[keep_cols].copy()

    if rename_map:
        df = df.rename(columns=rename_map)

    for col in df.columns:
        df[col] = df[col].astype(str).str.strip()

    df["record_id"] = df["record_id"].astype(str).str.strip()

    df["evaluator_email"] = df["evaluator_email"].replace("", DEFAULT_EMAIL)
    df["evaluator_email"] = df["evaluator_email"].fillna(DEFAULT_EMAIL)

    df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce")
    df["end_date"] = pd.to_datetime(df["end_date"], errors="coerce")

    # fill dates within each record_id
    df["start_date"] = df.groupby("record_id")["start_date"].transform(lambda s: s.ffill().bfill())
    df["end_date"] = df.groupby("record_id")["end_date"].transform(lambda s: s.ffill().bfill())
    
    df["name"] = df["name"].replace("", pd.NA)
    df["name"] = df.groupby("record_id")["name"].transform(lambda s: s.ffill().bfill())
    df["name"] = df["name"].fillna("")

    df["evaluation"] = df["evaluation"].astype(str).str.replace("*", "", regex=False).str.strip()
    df["evaluator"] = df["evaluator"].astype(str).str.strip()
    df["evaluator_email"] = df["evaluator_email"].astype(str).str.strip()

    df = df[df["evaluation"] != ""].copy()

    if eval_filter:
        df = df[df["evaluation"] == eval_filter].copy()

    df = df[df["start_date"].notna() | df["end_date"].notna()].copy()

    df = df[["record_id", "evaluator", "evaluator_email", "evaluation", "start_date", "end_date", "name"]]

    df.to_csv(output_path, index=False)
    print(f"Saved: {output_path}")

    return df

# raw preceptor matching -> simplified file
build_simplified_file(
    input_path=RAW_MATCH_PATH,
    output_path=MATCH_PATH,
    keep_cols=["record_id", "faculty_name", "faculty_email", "manual_evaluations", "start_date", "end_date", "name"],
    rename_map={
        "faculty_name": "evaluator",
        "faculty_email": "evaluator_email",
        "manual_evaluations": "evaluation",
    },
    eval_filter=MATCH_EVAL_FILTER
)

# raw oasis submission -> simplified file
build_simplified_file(
    input_path=RAW_EVAL_PATH,
    output_path=EVAL_PATH,
    keep_cols=["record_id", "evaluator", "evaluator_email", "evaluation", "start_date", "end_date","name"],
    rename_map=None,
    eval_filter=None
)

# ==============================
# STEP 2: LOAD SIMPLIFIED FILES
# ==============================
match_df = pd.read_csv(MATCH_PATH, dtype=str).fillna("")
eval_df = pd.read_csv(EVAL_PATH, dtype=str).fillna("")

for df in [match_df, eval_df]:
    for col in df.columns:
        df[col] = df[col].astype(str).str.strip()

match_df["record_id"] = match_df["record_id"].astype(str).str.strip()
eval_df["record_id"] = eval_df["record_id"].astype(str).str.strip()

match_df["faculty_name"] = match_df["evaluator"].apply(clean_name)
match_df["faculty_email"] = match_df["evaluator_email"].apply(normalize_email)
match_df["evaluation_type"] = match_df["evaluation"].apply(normalize_eval_name)

eval_df["faculty_name"] = eval_df["evaluator"].apply(clean_name)
eval_df["faculty_email"] = eval_df["evaluator_email"].apply(normalize_email)
eval_df["evaluation_type"] = eval_df["evaluation"].apply(normalize_eval_name)

match_df["start_date_parsed"] = pd.to_datetime(match_df["start_date"], errors="coerce")
match_df["end_date_parsed"] = pd.to_datetime(match_df["end_date"], errors="coerce")

eval_df["start_date_parsed"] = pd.to_datetime(eval_df["start_date"], errors="coerce")
eval_df["end_date_parsed"] = pd.to_datetime(eval_df["end_date"], errors="coerce")

# ==============================
# STEP 3: CHOOSE DATE
# ==============================
#if MANUAL_DATE:
#    test_date = pd.to_datetime(MANUAL_DATE).normalize()
#else:
#    test_date = pd.Timestamp.today().normalize()

#print(f"Using test date: {test_date.date()}")

# ==============================
# STEP 3: CHOOSE DATE
# ==============================
if MANUAL_DATE:
    test_date = pd.to_datetime(MANUAL_DATE).normalize()
    print("Using MANUAL date override")
else:
    test_date = (pd.Timestamp.today() - pd.Timedelta(days=GRACE_DAYS)).normalize()
    print(f"Using AUTO date (today - {GRACE_DAYS} days)")

print(f"Using test date: {test_date.date()}")

# ==============================
# STEP 4: FILTER TO ACTIVE MATCHES
# ==============================
active_matches = match_df[
    (match_df["start_date_parsed"].notna()) &
    (match_df["end_date_parsed"].notna()) &
    (match_df["start_date_parsed"] <= test_date) &
    (match_df["end_date_parsed"] >= test_date)
].copy()

if MATCH_EVAL_FILTER:
    active_matches = active_matches[
        active_matches["evaluation_type"] == MATCH_EVAL_FILTER
    ].copy()

active_matches = active_matches[
    active_matches["faculty_email"] != ""
].copy()

print(f"Active preceptor matching rows: {len(active_matches)}")

# ==============================
# STEP 5: FILTER COMPLETED EVALUATIONS
# ==============================
completed_evals = eval_df[
    eval_df["faculty_email"] != ""
].copy()

if EVAL_NAME_FILTER:
    completed_evals = completed_evals[
        completed_evals["evaluation_type"] == EVAL_NAME_FILTER
    ].copy()

print(f"Completed evaluation rows considered: {len(completed_evals)}")

# ==============================
# STEP 6: EXPECTED VS COMPLETED
# ==============================
expected = (
    active_matches
    .groupby(["record_id", "faculty_email", "evaluation_type"], dropna=False)
    .agg(
        student_name=("name", "first"),
        faculty_name=("faculty_name", "first"),
        start_date=("start_date", "first"),
        end_date=("end_date", "first"),
        expected_eval_count=("faculty_email", "size")
    )
    .reset_index()
)

completed = (
    completed_evals
    .groupby(["record_id", "faculty_email", "evaluation_type"], dropna=False)
    .agg(
        completed_eval_count=("faculty_email", "size")
    )
    .reset_index()
)

report = expected.merge(
    completed,
    on=["record_id", "faculty_email", "evaluation_type"],
    how="left"
)

report["completed_eval_count"] = report["completed_eval_count"].fillna(0).astype(int)
report["expected_eval_count"] = report["expected_eval_count"].fillna(0).astype(int)
report["pending_eval_count"] = report["expected_eval_count"] - report["completed_eval_count"]
report["pending_eval_count"] = report["pending_eval_count"].clip(lower=0)

report["duplicate_match_flag"] = report["expected_eval_count"].apply(lambda n: "YES" if n > 1 else "")
report["needs_reminder"] = report["pending_eval_count"].apply(lambda n: "YES" if n > 0 else "")

def build_note(row):
    if row["pending_eval_count"] <= 0:
        return ""

    if row["expected_eval_count"] == 1 and row["completed_eval_count"] == 0:
        return "The student reported working with you, but we have not yet received the corresponding evaluation."

    if row["expected_eval_count"] > 1 and row["completed_eval_count"] == 0:
        return (
            f"The student reported working with you on {row['expected_eval_count']} occasions, "
            f"but we have not yet received any completed evaluations."
        )

    if row["expected_eval_count"] > 1 and row["completed_eval_count"] < row["expected_eval_count"]:
        remaining = row["expected_eval_count"] - row["completed_eval_count"]
        return (
            f"The student reported working with you on {row['expected_eval_count']} occasions. "
            f"We have received {row['completed_eval_count']} completed evaluation(s) so far and are still missing {remaining}."
        )

    return ""

report["reminder_note"] = report.apply(build_note, axis=1)
report = report[report["needs_reminder"] == "YES"].copy()

# ==============================
# STEP 7: HISTORY
# ==============================
history_df = load_history(HISTORY_PATH)
report = remove_already_reminded(report, history_df)

history_update_df = report[["record_id", "faculty_email", "evaluation_type"]].copy()
update_history(HISTORY_PATH, history_update_df)

# ==============================
# STEP 8: LINKS
# ==============================
report["blank_form_link"] = report.apply(
    lambda row: make_prefill_link(row["student_name"], row["faculty_name"], partial=False),
    axis=1
)

report["partial_form_link"] = report.apply(
    lambda row: make_prefill_link(row["student_name"], row["faculty_name"], partial=True),
    axis=1
)

# ==============================
# STEP 9: FINAL OUTPUT
# ==============================
report = report[
    [   "faculty_email",
        "faculty_name",
        "student_name",
        "evaluation_type",
        "expected_eval_count",
        "completed_eval_count",
        "pending_eval_count",
        "duplicate_match_flag",
        "reminder_note",
        "blank_form_link",
        "partial_form_link"
    ]
].copy()

for col in report.columns:
    report[col] = (
        report[col]
        .fillna("")
        .astype(str)
        .str.replace(",", " -", regex=False)
        .str.replace('"', "", regex=False)
        .str.replace("\r", " ", regex=False)
        .str.replace("\n", " ", regex=False)
        .str.strip()
    )

report.to_csv(OUT_REMINDER_REPORT, index=False)

print(f"Saved reminder report to: {OUT_REMINDER_REPORT}")

print("\nPreceptors needing reminders:")
if report.empty:
    print("None")
else:
    print(report.to_string(index=False))
    
    
# ==============================
# STUDENT CHECKLIST ENTRIES REMINDER
# ==============================

# ==============================
# SETTINGS
# ==============================
CSV_PATH = r"C:\Users\ckrawiec\OneDrive - Penn State Health\PEDIATRICCLERKSHIPGR-ChecklistEntries_DATA_2026-03-12_1425.csv"

REQUIRED_ITEMS = [
    "[Ped] Acute Conditions e.g. Abdominal Pain, Fever, Seizure, Shortness of breath, Wheezing",
    "[Ped] Behavior e.g. Temper tantrums/aggressive behavior, ADHD, Developmental Delay, Autism Spectrum",
    "[Ped] Common Newborn Conditions e.g. Jaundice, Rash, Colic/Crying, Spit-up/Vomitting/Reflux, Poor Weight Gain",
    "[Ped] Dermatologic System e.g. Rash, Pallor",
    "[Ped] Gastrointestinal Tract",
    "[Ped] Health Supervision (Well Child Visit)",
    "[Ped] Health Systems Issue",
    "[Ped] Humanities Issue",
    "[Ped] Other e.g. Obesity/ Metabolic Syndrome",
    "[Ped] Upper and Lower Respiratory Tract e.g. Dental Caries, Sore Throat, Cough, Shortness of breath, Wheezing"
]

# These still must be present, but Observing is acceptable
OBSERVING_ALLOWED_ITEMS = [
    "[Ped] Health Systems Issue",
    "[Ped] Humanities Issue"
]

OUT_STUDENT_SUMMARY = r"C:\Users\ckrawiec\OneDrive - Penn State Health\CLERKSHIP_REMINDER_FOLDER\student_checklist_review.csv"

# Labels to use when complete
COMPLETE_LABEL = "All required items completed"
NO_OBSERVING_ISSUES_LABEL = "No observing-only issues"

# Use a delimiter that will not appear in your item text
PA_DELIM = "<br>"

# ==============================
# LOAD
# ==============================
df = pd.read_csv(CSV_PATH, dtype=str).fillna("")

# Clean whitespace
for col in df.columns:
    df[col] = df[col].astype(str).str.strip()

# Use the email column
email_col = "email"
print(f"Using email column: {email_col}")

# ==============================
# HELPERS
# ==============================
def first_nonblank(series):
    vals = [x for x in series if str(x).strip() != ""]
    return vals[0] if vals else ""

def sanitize_for_power_automate(text):
    """
    Remove line breaks and trim spaces so the text is safe for CSV/Flow handling.
    Also replaces the delimiter if it somehow appears in source text.
    """
    text = str(text).replace("\r", " ").replace("\n", " ").strip()
    text = " ".join(text.split())
    text = text.replace(PA_DELIM, "-")
    return text

def join_for_power_automate(items, empty_label):
    """
    Join list values using a Flow-safe delimiter instead of commas.
    """
    cleaned = [sanitize_for_power_automate(x) for x in items if str(x).strip()]
    return PA_DELIM.join(cleaned) if cleaned else empty_label

def clean_item_label(text):
    """
    Makes checklist items Power Automate safe.
    Removes commas so Flow split(',') works correctly.
    """
    text = str(text).strip()
    text = text.replace(",", " -")
    text = " ".join(text.split())
    return text

# ==============================
# FILL start_date / end_date / name / email BY record_id
# ==============================
parent_map = (
    df.groupby("record_id", dropna=False)
      .agg({
          "start_date": first_nonblank,
          "end_date": first_nonblank,
          "name": first_nonblank,
          email_col: first_nonblank
      })
      .reset_index()
      .rename(columns={email_col: "email"})
)

drop_cols = ["start_date", "end_date", "name", "email"]
df = df.drop(columns=[c for c in drop_cols if c in df.columns], errors="ignore")
df = df.merge(parent_map, on="record_id", how="left")

# Parse rotation dates
df["start_date_parsed"] = pd.to_datetime(df["start_date"], errors="coerce")
df["end_date_parsed"] = pd.to_datetime(df["end_date"], errors="coerce")

# ==============================
# CHOOSE DATE
# ==============================
if MANUAL_DATE:
    test_date = pd.to_datetime(MANUAL_DATE).normalize()
    print("Using MANUAL date override")
else:
    test_date = (pd.Timestamp.today() - pd.Timedelta(days=GRACE_DAYS)).normalize()
    print(f"Using AUTO date (today - {GRACE_DAYS} days)")

print(f"Using test date: {test_date.date()}")

# ==============================
# FILTER TO ACTIVE STUDENTS
# ==============================
active_df = df[
    (df["start_date_parsed"].notna()) &
    (df["end_date_parsed"].notna()) &
    (df["start_date_parsed"] <= test_date) &
    (df["end_date_parsed"] >= test_date)
].copy()

print(f"Rows belonging to active students on {test_date.date()}: {len(active_df)}")

# Build a one-row-per-student list of all active students
active_students = (
    active_df.groupby(["record_id", "name", "email"], dropna=False)
    .size()
    .reset_index(name="row_count")
    .drop(columns="row_count")
)

print(f"Active students on {test_date.date()}: {len(active_students)}")

# Checklist entries only
active_entries = active_df[
    active_df["redcap_repeat_instrument"].astype(str).str.strip().eq("checklist_entry")
].copy()

print(f"Checklist entry rows for active students: {len(active_entries)}")

active_entries["student_activity_clean"] = (
    active_entries["student_activity"]
    .astype(str)
    .str.strip()
    .str.lower()
)

active_entries["item"] = active_entries["item"].astype(str).str.strip()

# ==============================
# BUILD STUDENT SUMMARY
# ==============================
rows = []

for _, student in active_students.iterrows():
    record_id = student["record_id"]
    name = student["name"]
    email = student["email"]

    group = active_entries[active_entries["record_id"] == record_id].copy()

    row = {
        "record_id": record_id,
        "name": name,
        "email": email
    }

    missing_items = []
    observing_only_items = []

    for item in REQUIRED_ITEMS:
        item_rows = group[group["item"] == item].copy()

        has_item = not item_rows.empty
        has_observing = has_item and item_rows["student_activity_clean"].eq("observing").any()
        has_non_observing = has_item and (~item_rows["student_activity_clean"].eq("observing")).any()

        is_missing = not has_item
        is_observing_only = (
            has_item and
            has_observing and
            not has_non_observing and
            item not in OBSERVING_ALLOWED_ITEMS
        )

        if is_missing:
            missing_items.append(clean_item_label(item))

        if is_observing_only:
            observing_only_items.append(clean_item_label(item))

    # Human-readable fields
    row["missing_items"] = PA_DELIM.join(missing_items) if missing_items else COMPLETE_LABEL
    row["observing_only_items"] = join_for_power_automate(observing_only_items, NO_OBSERVING_ISSUES_LABEL)

    # Explicit Power Automate delimiter fields
    row["missing_items_delimiter"] = PA_DELIM
    row["observing_only_items_delimiter"] = PA_DELIM

    # Optional overall status
    if missing_items or observing_only_items:
        row["status"] = "Needs review"
    else:
        row["status"] = "Complete"

    # Optional count fields
    row["missing_count"] = len(missing_items)
    row["observing_only_count"] = len(observing_only_items)

    rows.append(row)

student_summary = pd.DataFrame(rows)

student_summary = student_summary.sort_values(["name", "record_id"]).reset_index(drop=True)

# ==============================
# SAVE
# ==============================
student_summary.to_csv(OUT_STUDENT_SUMMARY, index=False)

print(f"Saved student summary to: {OUT_STUDENT_SUMMARY}")

print("\nStudent checklist summary:")
if student_summary.empty:
    print("No active students found for this date.")
else:
    print(student_summary.to_string(index=False))
    
    
    
import pandas as pd
from pathlib import Path
from urllib.parse import quote_plus

# ==============================
# OBSERVED HP PRECEPTOR REMINDER
# ==============================

import pandas as pd
from pathlib import Path
from urllib.parse import quote_plus

# ==============================
# OBSERVED HP PRECEPTOR REMINDER
# ==============================

# ==============================
# SETTINGS
# ==============================
RAW_MATCH_PATH = r"C:\Users\ckrawiec\OneDrive - Penn State Health\PEDIATRICCLERKSHIPGR-PreceptorMatching_DATA_2026-03-09_0829.csv"
RAW_EPA_PATH   = r"C:\Users\ckrawiec\OneDrive - Penn State Health\PEDIATRICCLERKSHIPGR-EPA_DATA_2026-03-09_0829.csv"

MATCH_PATH = r"C:\Users\ckrawiec\OneDrive - Penn State Health\preceptor_match_hp_review.csv"
EPA_PATH   = r"C:\Users\ckrawiec\OneDrive - Penn State Health\epa_hp_submission.csv"

OUT_REMINDER_REPORT = r"C:\Users\ckrawiec\OneDrive - Penn State Health\CLERKSHIP_REMINDER_FOLDER\observed_hp_reminders.csv"
HISTORY_PATH = r"C:\Users\ckrawiec\OneDrive - Penn State Health\preceptor_reminder_history.csv"

# ==============================
# SETTINGS - DELETE
# ==============================
#RAW_MATCH_PATH = "PEDIATRICCLERKSHIPGR-PreceptorMatching_DATA_2026-03-09_0829.csv"
#RAW_EPA_PATH   = "PEDIATRICCLERKSHIPGR-EPA_DATA_2026-03-09_0829.csv"

#MATCH_PATH = "preceptor_match_hp_review.csv"
#EPA_PATH   = "epa_hp_submission.csv"

#OUT_REMINDER_REPORT = "observed_hp_reminders.csv"
#HISTORY_PATH = "preceptor_reminder_history.csv"

# ==============================
MATCH_EVAL_FILTER = "PEDS History Taking & Physical Exam"
EPA_NAME_FILTER   = "PEDS History Taking & Physical Exam"

DEFAULT_EMAIL = "ckrawiec@pennstatehealth.psu.edu"
# ==============================

# ==============================
# HELPERS
# ==============================
def normalize_email(s):
    return str(s).strip().lower()

def normalize_eval_name(s):
    return str(s).strip().lstrip("*").strip()

def clean_name(s):
    s = str(s).strip()

    if ";" in s:
        s = s.split(";")[0].strip()

    if " - " in s:
        last, first = s.split(" - ", 1)
        first = first.strip().split()[0]
        return f"{first} {last.strip()}"

    if "," in s:
        last, first = s.split(",", 1)
        first = first.strip().split()[0]
        return f"{first} {last.strip()}"

    return s

def make_prefill_link(student_name, faculty_name, partial=False):
    base = "https://redcap.ctsi.psu.edu/surveys/?s=8C7DLPNX8LT9HTJP"

    student = quote_plus(str(student_name).strip())
    preceptor = quote_plus(str(faculty_name).strip())

    url = f"{base}&student={student}&preceptor={preceptor}"

    if partial:
        url += "&complete=1&ph=3&ch=3&pp=3&cp=3"

    return url

def load_history(history_path):
    history_file = Path(history_path)

    if not history_file.exists():
        return pd.DataFrame(columns=["record_id", "faculty_email", "evaluation_type"])

    try:
        hist = pd.read_csv(history_file, dtype=str).fillna("")
    except Exception as e:
        print(f"Could not read history file: {e}")
        return pd.DataFrame(columns=["record_id", "faculty_email", "evaluation_type"])

    for col in ["record_id", "faculty_email", "evaluation_type"]:
        if col not in hist.columns:
            hist[col] = ""

    hist["record_id"] = hist["record_id"].astype(str).str.strip()
    hist["faculty_email"] = hist["faculty_email"].apply(normalize_email)
    hist["evaluation_type"] = hist["evaluation_type"].astype(str).str.strip()

    return hist[["record_id", "faculty_email", "evaluation_type"]].drop_duplicates().reset_index(drop=True)

def remove_already_reminded(current_report, history_df):
    if current_report.empty:
        return current_report

    current_report = current_report.copy()
    current_report["record_id"] = current_report["record_id"].astype(str).str.strip()
    current_report["faculty_email_norm"] = current_report["faculty_email"].apply(normalize_email)
    current_report["evaluation_type"] = current_report["evaluation_type"].astype(str).str.strip()

    history_keys = set(
        zip(
            history_df["record_id"],
            history_df["faculty_email"],
            history_df["evaluation_type"]
        )
    )

    before = len(current_report)

    current_report = current_report[
        ~current_report.apply(
            lambda row: (
                row["record_id"],
                row["faculty_email_norm"],
                row["evaluation_type"]
            ) in history_keys,
            axis=1
        )
    ].copy()

    after = len(current_report)
    print(f"Removed {before - after} reminder(s) already found in history.")

    return current_report.drop(columns=["faculty_email_norm"], errors="ignore")

def update_history(history_path, reminders_sent_df):
    history_file = Path(history_path)

    if reminders_sent_df.empty:
        if not history_file.exists():
            pd.DataFrame(columns=["record_id", "faculty_email", "evaluation_type"]).to_csv(history_file, index=False)
        return

    new_hist = reminders_sent_df[["record_id", "faculty_email", "evaluation_type"]].copy()
    new_hist["record_id"] = new_hist["record_id"].astype(str).str.strip()
    new_hist["faculty_email"] = new_hist["faculty_email"].apply(normalize_email)
    new_hist["evaluation_type"] = new_hist["evaluation_type"].astype(str).str.strip()
    new_hist = new_hist.drop_duplicates()

    old_hist = load_history(history_path)

    combined = pd.concat([old_hist, new_hist], ignore_index=True)
    combined = combined.drop_duplicates().sort_values(
        ["record_id", "faculty_email", "evaluation_type"]
    ).reset_index(drop=True)

    combined.to_csv(history_file, index=False)
    print(f"Updated history file: {history_path}")

# ==============================
# BUILD SIMPLIFIED FILES
# ==============================
def build_simplified_file(
    input_path,
    output_path,
    keep_cols,
    rename_map=None,
    eval_filter=None
):
    df = pd.read_csv(input_path, dtype=str).fillna("")
    df = df[keep_cols].copy()

    if rename_map:
        df = df.rename(columns=rename_map)

    for col in df.columns:
        df[col] = df[col].astype(str).str.strip()

    df["record_id"] = df["record_id"].astype(str).str.strip()

    df["evaluator_email"] = df["evaluator_email"].replace("", DEFAULT_EMAIL)
    df["evaluator_email"] = df["evaluator_email"].fillna(DEFAULT_EMAIL)

    df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce")
    df["end_date"] = pd.to_datetime(df["end_date"], errors="coerce")

    df["start_date"] = df.groupby("record_id")["start_date"].transform(lambda s: s.ffill().bfill())
    df["end_date"] = df.groupby("record_id")["end_date"].transform(lambda s: s.ffill().bfill())
    
    df["name"] = df["name"].replace("", pd.NA)
    df["name"] = df.groupby("record_id")["name"].transform(lambda s: s.ffill().bfill())
    df["name"] = df["name"].fillna("")

    df["evaluation"] = df["evaluation"].astype(str).str.replace("*", "", regex=False).str.strip()
    df["evaluator"] = df["evaluator"].astype(str).str.strip()
    df["evaluator_email"] = df["evaluator_email"].astype(str).str.strip()

    df = df[df["evaluation"] != ""].copy()

    if eval_filter:
        df = df[df["evaluation"] == eval_filter].copy()

    df = df[df["start_date"].notna() | df["end_date"].notna()].copy()

    df = df[["record_id", "evaluator", "evaluator_email", "evaluation", "start_date", "end_date", "name"]]

    df.to_csv(output_path, index=False)
    print(f"Saved: {output_path}")

    return df

# Raw preceptor matching -> simplified H&P review file
build_simplified_file(
    input_path=RAW_MATCH_PATH,
    output_path=MATCH_PATH,
    keep_cols=["record_id", "faculty_name", "faculty_email", "manual_evaluations", "start_date", "end_date","name"],
    rename_map={
        "faculty_name": "evaluator",
        "faculty_email": "evaluator_email",
        "manual_evaluations": "evaluation"
    },
    eval_filter=MATCH_EVAL_FILTER
)

# Raw EPA -> simplified EPA submission file
build_simplified_file(
    input_path=RAW_EPA_PATH,
    output_path=EPA_PATH,
    keep_cols=["record_id", "epa_evaluator", "epa_evaluator_email", "epa_evaluation", "start_date", "end_date","name"],
    rename_map={
        "epa_evaluator": "evaluator",
        "epa_evaluator_email": "evaluator_email",
        "epa_evaluation": "evaluation"
    },
    eval_filter=None
)

# ==============================
# LOAD SIMPLIFIED FILES
# ==============================
match_df = pd.read_csv(MATCH_PATH, dtype=str).fillna("")
epa_df = pd.read_csv(EPA_PATH, dtype=str).fillna("")

for df in [match_df, epa_df]:
    for col in df.columns:
        df[col] = df[col].astype(str).str.strip()

match_df["record_id"] = match_df["record_id"].astype(str).str.strip()
epa_df["record_id"] = epa_df["record_id"].astype(str).str.strip()

match_df["faculty_name"] = match_df["evaluator"].apply(clean_name)
match_df["faculty_email"] = match_df["evaluator_email"].apply(normalize_email)
match_df["evaluation_type"] = match_df["evaluation"].apply(normalize_eval_name)

epa_df["faculty_name"] = epa_df["evaluator"].apply(clean_name)
epa_df["faculty_email"] = epa_df["evaluator_email"].apply(normalize_email)
epa_df["evaluation_type"] = epa_df["evaluation"].apply(normalize_eval_name)

match_df["start_date_parsed"] = pd.to_datetime(match_df["start_date"], errors="coerce")
match_df["end_date_parsed"] = pd.to_datetime(match_df["end_date"], errors="coerce")

epa_df["start_date_parsed"] = pd.to_datetime(epa_df["start_date"], errors="coerce")
epa_df["end_date_parsed"] = pd.to_datetime(epa_df["end_date"], errors="coerce")

# ==============================
# CHOOSE DATE
# ==============================
#if MANUAL_DATE:
#    test_date = pd.to_datetime(MANUAL_DATE).normalize()
#else:
#    test_date = pd.Timestamp.today().normalize()

#print(f"Using test date: {test_date.date()}")

# ==============================
# STEP 3: CHOOSE DATE
# ==============================
if MANUAL_DATE:
    test_date = pd.to_datetime(MANUAL_DATE).normalize()
    print("Using MANUAL date override")
else:
    test_date = (pd.Timestamp.today() - pd.Timedelta(days=GRACE_DAYS)).normalize()
    print(f"Using AUTO date (today - {GRACE_DAYS} days)")

print(f"Using test date: {test_date.date()}")

# ==============================
# FILTER TO ACTIVE MATCHES
# ==============================
active_matches = match_df[
    (match_df["start_date_parsed"].notna()) &
    (match_df["end_date_parsed"].notna()) &
    (match_df["start_date_parsed"] <= test_date) &
    (match_df["end_date_parsed"] >= test_date)
].copy()

if MATCH_EVAL_FILTER:
    active_matches = active_matches[
        active_matches["evaluation_type"] == MATCH_EVAL_FILTER
    ].copy()

active_matches = active_matches[
    active_matches["faculty_email"] != ""
].copy()

print(f"Active H&P matching rows: {len(active_matches)}")

# ==============================
# FILTER COMPLETED EPA SUBMISSIONS
# ==============================
completed_epas = epa_df[
    epa_df["faculty_email"] != ""
].copy()

if EPA_NAME_FILTER:
    completed_epas = completed_epas[
        completed_epas["evaluation_type"] == EPA_NAME_FILTER
    ].copy()

print(f"Completed H&P EPA rows considered: {len(completed_epas)}")

# ==============================
# EXPECTED VS COMPLETED
# ==============================
expected = (
    active_matches
    .groupby(["record_id", "faculty_email", "evaluation_type"], dropna=False)
    .agg(
        student_name=("name", "first"),
        faculty_name=("faculty_name", "first"),
        start_date=("start_date", "first"),
        end_date=("end_date", "first"),
        expected_eval_count=("faculty_email", "size")
    )
    .reset_index()
)

completed = (
    completed_epas
    .groupby(["record_id", "faculty_email", "evaluation_type"], dropna=False)
    .agg(
        completed_eval_count=("faculty_email", "size")
    )
    .reset_index()
)

report = expected.merge(
    completed,
    on=["record_id", "faculty_email", "evaluation_type"],
    how="left"
)

report["completed_eval_count"] = report["completed_eval_count"].fillna(0).astype(int)
report["expected_eval_count"] = report["expected_eval_count"].fillna(0).astype(int)
report["pending_eval_count"] = report["expected_eval_count"] - report["completed_eval_count"]
report["pending_eval_count"] = report["pending_eval_count"].clip(lower=0)

report["duplicate_match_flag"] = report["expected_eval_count"].apply(lambda n: "YES" if n > 1 else "")
report["needs_reminder"] = report["pending_eval_count"].apply(lambda n: "YES" if n > 0 else "")

def build_note(row):
    expected = row["expected_eval_count"]
    completed = row["completed_eval_count"]

    if row["pending_eval_count"] <= 0:
        return ""

    if expected == 1 and completed == 0:
        return "The student indicated that you observed an H&P encounter with them, but we have not yet received the corresponding formative assessment."

    if expected > 1 and completed == 0:
        return f"The student indicated that you observed {expected} H&P encounters with them, but we have not yet received any formative assessments."

    if expected > 1 and completed < expected:
        remaining = expected - completed
        return f"The student indicated that you observed {expected} H&P encounters with them. We have received {completed} submission(s) so far and are still missing {remaining}."

    return ""

report["reminder_note"] = report.apply(build_note, axis=1)
report = report[report["needs_reminder"] == "YES"].copy()

# ==============================
# HISTORY
# ==============================
report["evaluation_type"] = "PEDS History Taking & Physical Exam"

history_df = load_history(HISTORY_PATH)
report = remove_already_reminded(report, history_df)

history_update_df = report[["record_id", "faculty_email", "evaluation_type"]].copy()
update_history(HISTORY_PATH, history_update_df)

# ==============================
# LINKS
# ==============================
report["blank_form_link"] = report.apply(
    lambda row: make_prefill_link(row["student_name"], row["faculty_name"], partial=False),
    axis=1
)

report["partial_form_link"] = report.apply(
    lambda row: make_prefill_link(row["student_name"], row["faculty_name"], partial=True),
    axis=1
)

# ==============================
# FINAL OUTPUT
# ==============================
report = report[
    [
        "faculty_email",
        "faculty_name",
        "student_name",
        "reminder_note",
        "blank_form_link",
        "partial_form_link"
    ]
].copy()

for col in report.columns:
    report[col] = (
        report[col]
        .fillna("")
        .astype(str)
        .str.replace(",", " -", regex=False)
        .str.replace('"', "", regex=False)
        .str.replace("\r", " ", regex=False)
        .str.replace("\n", " ", regex=False)
        .str.strip()
    )

report.to_csv(OUT_REMINDER_REPORT, index=False)

print(f"Saved reminder report to: {OUT_REMINDER_REPORT}")

print("\nPreceptors needing Observed H&P reminders:")
if report.empty:
    print("None")
else:
    print(report.to_string(index=False))

# ========================================
# STUDENT FEEDBACK SOLICITATION REMINDERS
# ========================================
import pandas as pd
import numpy as np
from pathlib import Path
import re

# ==============================
# SETTINGS
# ==============================
OASIS_PATH = r"C:\Users\ckrawiec\OneDrive - Penn State Health\PEDIATRICCLERKSHIPGR-OasisEvaluation_DATA_2026-03-09_0829.csv"
EPA_PATH   = r"C:\Users\ckrawiec\OneDrive - Penn State Health\PEDIATRICCLERKSHIPGR-EPA_DATA_2026-03-09_0829.csv"
MATCH_PATH = r"C:\Users\ckrawiec\OneDrive - Penn State Health\PEDIATRICCLERKSHIPGR-PreceptorMatching_DATA_2026-03-09_0829.csv"

base_dir = Path(r"C:\Users\ckrawiec\OneDrive - Penn State Health\CLERKSHIP_REMINDER_FOLDER")

#as_of_date = pd.to_datetime(MANUAL_DATE).normalize() if MANUAL_DATE else pd.Timestamp.today().normalize()
#print("As of date:", as_of_date.date())

as_of_date = (
    pd.to_datetime(MANUAL_DATE).normalize()
    if MANUAL_DATE
    else (pd.Timestamp.today() - pd.Timedelta(days=GRACE_DAYS)).normalize()
)

print("As of date:", as_of_date.date())

PEDS_HANDOFF_REQUIRED = 1

# ==============================
# HELPERS
# ==============================
def parse_date(x):
    if pd.isna(x) or str(x).strip() == "":
        return pd.NaT
    return pd.to_datetime(x, errors="coerce").normalize()


def first_nonblank(series):
    for x in series:
        if pd.notna(x) and str(x).strip() != "":
            return x
    return ""


def normalize_eval_name(x):
    if pd.isna(x):
        return ""
    s = str(x).strip()
    s = re.sub(r"^\*+", "", s)
    return s.lower()


def is_hp(x):
    return "peds history taking & physical exam" in normalize_eval_name(x)


def is_cas(x):
    return "clinical assessment of student" in normalize_eval_name(x)


def clean_person_name(x):
    if pd.isna(x):
        return ""

    s = str(x).strip()
    if not s:
        return ""

    s = s.split(";")[0].strip()
    s = re.sub(r"\s+", " ", s)

    if " - " in s:
        last, first = s.split(" - ", 1)
        return f"{first.strip().title()} {last.strip().title()}".strip()

    if "," in s:
        last, first = s.split(",", 1)
        return f"{first.strip().title()} {last.strip().title()}".strip()

    return s.title()


def format_faculty_list(faculty_list):
    if isinstance(faculty_list, list) and faculty_list:
        if len(faculty_list) == 1:
            return faculty_list[0]
        return ", ".join(faculty_list[:-1]) + f", and {faculty_list[-1]}"
    return ""


def format_faculty_list_power_automate(faculty_list):
    faculty_list = [str(x).strip() for x in faculty_list if str(x).strip() != ""]

    if not faculty_list:
        return ""

    if len(faculty_list) == 1:
        return faculty_list[0]

    if len(faculty_list) == 2:
        return f"{faculty_list[0]} and {faculty_list[1]}"

    return " ; ".join(faculty_list[:-1]) + f" ; and {faculty_list[-1]}"


def build_reminder_ob(row):

    if row["hp_count"] >= 2:
        return (
            "Observed H&P requirement complete. Thank you for documenting your observed history and physical experiences."
        )

    faculty_text = format_faculty_list_power_automate(row.get("hp_faculty_list", []))

    faculty_sentence = (
        f" Documented observed history and physical activity is currently associated with {faculty_text}."
        if faculty_text else ""
    )

    text = (
        f"Observed H&P - our records currently show {row['hp_count']} documented solicitations or submissions."
        f"{faculty_sentence} "
        f"Students are expected to have 2 documented observed history and physical solicitations or submissions during the clerkship."
    )

    text = (
        str(text)
        .replace(",", "")
        .replace('"', "")
        .replace("\n", " ")
        .replace("\r", " ")
        .strip()
    )

    return re.sub(r"\s+", " ", text)

def build_reminder_cas(row):

    if row["cas_count"] >= 8:
        return (
            "Clinical Assessment of Student requirement complete. Thank you for consistently requesting and documenting feedback during the clerkship."
        )

    faculty_text = format_faculty_list_power_automate(row.get("cas_faculty_list", []))

    faculty_sentence = (
        f" Documented Clinical Assessment of Student activity is currently associated with {faculty_text}."
        if faculty_text else ""
    )

    text = (
        f"Clinical Assessment of Student - our records currently show {row['cas_count']} documented solicitations or submissions."
        f"{faculty_sentence} "
        f"Students are expected to have 8 documented Clinical Assessment of Student solicitations or submissions during the clerkship."
    )

    text = (
        str(text)
        .replace(",", "")
        .replace('"', "")
        .replace("\n", " ")
        .replace("\r", " ")
        .strip()
    )

    return re.sub(r"\s+", " ", text)

def is_handoff(x):
    return "peds handoff" in normalize_eval_name(x)

def build_reminder_handoff(row):

    if row["handoff_count"] >= PEDS_HANDOFF_REQUIRED:
        return (
            "Pediatric Clerkship Handoff requirement complete. Thank you for documenting your handoff experience during the clerkship."
        )

    faculty_text = format_faculty_list_power_automate(row.get("handoff_faculty_list", []))

    faculty_sentence = (
        f" Documented Pediatric Clerkship Handoff activity is currently associated with {faculty_text}."
        if faculty_text else ""
    )

    text = (
        f"Pediatric Clerkship Handoff - our records currently show {row['handoff_count']} documented solicitation or submission."
        f"{faculty_sentence} "
        f"Students are expected to have {PEDS_HANDOFF_REQUIRED} documented Pediatric Clerkship Handoff solicitation or submission during the clerkship."
    )

    text = (
        str(text)
        .replace(",", "")
        .replace('"', "")
        .replace("\n", " ")
        .replace("\r", " ")
        .strip()
    )

    return re.sub(r"\s+", " ", text)

# ==============================
# LOAD FILES
# ==============================
epa_df = pd.read_csv(base_dir / EPA_PATH)
oasis_df = pd.read_csv(base_dir / OASIS_PATH)
match_df = pd.read_csv(base_dir / MATCH_PATH)

print("EPA rows:", len(epa_df))
print("OASIS rows:", len(oasis_df))
print("MATCH rows:", len(match_df))


# ==============================
# BUILD ROSTER
# ==============================
roster = pd.concat([
    epa_df.loc[
        epa_df["start_date"].notna(),
        ["record_id", "email", "student_name", "start_date", "end_date"]
    ].copy(),
    oasis_df.loc[
        oasis_df["start_date"].notna(),
        ["record_id", "email", "name", "start_date", "end_date"]
    ].rename(columns={"name": "student_name"}).copy(),
    match_df.loc[
        match_df["start_date"].notna(),
        ["record_id", "email", "name", "start_date", "end_date"]
    ].rename(columns={"name": "student_name"}).copy()
], ignore_index=True)

roster = roster.groupby("record_id", as_index=False).agg({
    "email": first_nonblank,
    "student_name": first_nonblank,
    "start_date": first_nonblank,
    "end_date": first_nonblank
})

roster["start_date"] = roster["start_date"].apply(parse_date)
roster["end_date"] = roster["end_date"].apply(parse_date)

active_roster = roster[
    (roster["start_date"].notna()) &
    (roster["end_date"].notna()) &
    (roster["start_date"] <= as_of_date) &
    (roster["end_date"] >= as_of_date)
].copy()

print("Active students:", len(active_roster))


# ==============================
# H&P EVENTS
# Count as one if same record_id + same faculty_clean
# ==============================
match_hp = match_df[
    (match_df["redcap_repeat_instrument"].fillna("").str.strip() == "preceptor_matching") &
    (match_df["manual_evaluations"].apply(is_hp))
].copy()

match_hp["faculty_clean"] = match_hp["faculty_name"].apply(clean_person_name)
match_hp = match_hp[["record_id", "faculty_clean"]]

epa_hp = epa_df[
    epa_df["epa_evaluation"].apply(is_hp)
].copy()

epa_hp["faculty_clean"] = epa_hp["epa_evaluator"].apply(clean_person_name)
epa_hp = epa_hp[["record_id", "faculty_clean"]]

hp_events = pd.concat([match_hp, epa_hp], ignore_index=True)
hp_events = hp_events.drop_duplicates(subset=["record_id", "faculty_clean"])

hp_summary = (
    hp_events.groupby("record_id", as_index=False)
    .agg(
        hp_count=("faculty_clean", "size"),
        hp_faculty_list=("faculty_clean", lambda s: sorted([x for x in s if str(x).strip() != ""]))
    )
)

print("Unique H&P events:", len(hp_events))


# ==============================
# CAS EVENTS
# Count as one if same record_id + same faculty_clean
# ==============================
match_cas = match_df[
    (match_df["redcap_repeat_instrument"].fillna("").str.strip() == "preceptor_matching") &
    (match_df["manual_evaluations"].apply(is_cas))
].copy()

match_cas["faculty_clean"] = match_cas["faculty_name"].apply(clean_person_name)
match_cas = match_cas[["record_id", "faculty_clean"]]

oasis_cas = oasis_df[
    oasis_df["evaluation"].apply(is_cas)
].copy()

oasis_cas["faculty_clean"] = oasis_cas["evaluator"].apply(clean_person_name)
oasis_cas = oasis_cas[["record_id", "faculty_clean"]]

cas_events = pd.concat([match_cas, oasis_cas], ignore_index=True)
cas_events = cas_events.drop_duplicates(subset=["record_id", "faculty_clean"])

cas_summary = (
    cas_events.groupby("record_id", as_index=False)
    .agg(
        cas_count=("faculty_clean", "size"),
        cas_faculty_list=("faculty_clean", lambda s: sorted([x for x in s if str(x).strip() != ""]))
    )
)

print("Unique CAS events:", len(cas_events))

# ==============================
# PEDS HANDOFF EVENTS
# Count as one if same record_id + same faculty_clean
# ==============================
match_handoff = match_df[
    (match_df["redcap_repeat_instrument"].fillna("").str.strip() == "preceptor_matching") &
    (match_df["manual_evaluations"].apply(is_handoff))
].copy()

match_handoff["faculty_clean"] = match_handoff["faculty_name"].apply(clean_person_name)
match_handoff = match_handoff[["record_id", "faculty_clean"]]

epa_handoff = epa_df[
    epa_df["epa_evaluation"].apply(is_handoff)
].copy()

epa_handoff["faculty_clean"] = epa_handoff["epa_evaluator"].apply(clean_person_name)
epa_handoff = epa_handoff[["record_id", "faculty_clean"]]

handoff_events = pd.concat([match_handoff, epa_handoff], ignore_index=True)
handoff_events = handoff_events.drop_duplicates(subset=["record_id", "faculty_clean"])

handoff_summary = (
    handoff_events.groupby("record_id", as_index=False)
    .agg(
        handoff_count=("faculty_clean", "size"),
        handoff_faculty_list=("faculty_clean", lambda s: sorted([x for x in s if str(x).strip() != ""]))
    )
)

print("Unique PEDS Handoff events:", len(handoff_events))

# ==============================
# BUILD REPORT
# ==============================
report = active_roster.merge(hp_summary, on="record_id", how="left")
report = report.merge(cas_summary, on="record_id", how="left")
report = report.merge(handoff_summary, on="record_id", how="left")

report["hp_count"] = report["hp_count"].fillna(0).astype(int)
report["cas_count"] = report["cas_count"].fillna(0).astype(int)
report["handoff_count"] = report["handoff_count"].fillna(0).astype(int)

report["hp_faculty_list"] = report["hp_faculty_list"].apply(lambda x: x if isinstance(x, list) else [])
report["cas_faculty_list"] = report["cas_faculty_list"].apply(lambda x: x if isinstance(x, list) else [])
report["handoff_faculty_list"] = report["handoff_faculty_list"].apply(lambda x: x if isinstance(x, list) else [])

import random
from urllib.parse import quote

def pick_random_preceptor(row):
    all_preceptors = (
        row["hp_faculty_list"] +
        row["cas_faculty_list"] +
        row["handoff_faculty_list"]
    )

    # remove blanks and duplicates
    all_preceptors = sorted(set([str(x).strip() for x in all_preceptors if str(x).strip() != ""]))

    if not all_preceptors:
        return ""

    return random.choice(all_preceptors)

report["random_preceptor"] = report.apply(pick_random_preceptor, axis=1)

report["preceptor_shoutout"] = report["random_preceptor"].apply(
    lambda x: f"https://redcap.ctsi.psu.edu/surveys/?s=YHLPMA48Y9HNWKCA&des=1&preceptor_name={quote(x)}" if x else ""
)

report["reminder_needed"] = np.where(
    (report["hp_count"] < 2) | (report["cas_count"] < 8) | (report["handoff_count"] < PEDS_HANDOFF_REQUIRED),
    "Yes",
    "No"
)

report["reminderob"] = report.apply(build_reminder_ob, axis=1)
report["remindercas"] = report.apply(build_reminder_cas, axis=1)
report["reminderhandoff"] = report.apply(build_reminder_handoff, axis=1)

report = report[[
    "record_id",
    "student_name",
    "email",
    "start_date",
    "end_date",
    "hp_count",
    "cas_count",
    "handoff_count",
    "reminder_needed",
    "reminderob",
    "remindercas",
    "reminderhandoff",
    "random_preceptor",
    "preceptor_shoutout"
]].sort_values(["start_date", "student_name"])

print(report.to_string(index=False))

reminders = report[
    report["reminder_needed"] == "Yes"
][[
    "record_id",
    "student_name",
    "email",
    "reminderob",
    "remindercas",
    "reminderhandoff",
    "random_preceptor",
    "preceptor_shoutout"
]].copy()

reminders.to_csv(base_dir / "feedback_reminders_power_automate.csv", index=False)
print("Saved: feedback_reminders_power_automate.csv")