from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from typing import Iterable
from urllib.parse import quote_plus

import pandas as pd
import streamlit as st


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

st.title("📋 OASIS Preceptor Evaluation Reminder Builder — MULTI-FORM v2")
st.caption("VERSION: MULTI-FORM v2 — tracks Clinical Assessment of Student AND Observed H&P / PEDS History Taking & Physical Exam")
st.write(
    "Upload the raw OASIS evaluation export and the raw evaluation associations/preceptor matching file. "
    "The app cross-references expected evaluations against submitted evaluations and generates a "
    "Power Automate-ready reminder CSV."
)

EVAL_CONFIG_BY_KEY, LABEL_TO_KEY = config_maps(EVAL_CONFIGS)
DEFAULT_LABELS = [c.label for c in EVAL_CONFIGS]

with st.sidebar:
    st.success("✅ MULTI-FORM v2 LOADED")
    st.caption("You should see checkboxes/multiselect for CAS and Observed H&P below. If not, you are running an old file.")
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

with tab1:
    st.subheader("Combined Power Automate-ready reminder file")
    st.dataframe(reminders, use_container_width=True)

    csv_bytes = reminders.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="Download combined_preceptor_eval_reminders.csv",
        data=csv_bytes,
        file_name="combined_preceptor_eval_reminders.csv",
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
