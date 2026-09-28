# Your app, separated into easy-to-find files

Your Streamlit main file is still **app2627.py**. It now contains 64 lines: the
original page setup, the same dropdown and header, and the code that opens the
selected section. Each dropdown section has its own Python file in the
**instruments** folder.

The original section bodies were copied without changing their code. Each one
is inside a `render()` function, which the main app calls on every Streamlit
rerun. The sections retain their existing uploads, fields, buttons, calculations,
filenames, column orders, downloads, and saved-data behavior.

## Upload to your existing GitHub repository

1. **Extract the ZIP on your computer.** Upload the extracted files, rather than
   the ZIP itself.
2. In the same repository location as your current `app2627.py`, replace that
   file with the new **app2627.py** and add the complete **instruments** folder.
   Include **instruments/__init__.py** and all ten section files. Upload the main
   file and the whole folder together in the same commit.
3. Keep Streamlit's main file path set to **app2627.py**. If your existing app is
   inside a repository subfolder, place the new main file there and put the
   instruments folder beside it; retain the existing main file path setting.
4. Keep your existing **assets** folder, saved data, **requirements.txt**, Python
   version, and Streamlit Secrets. This split does not require new dependencies
   or configuration changes.
5. Commit the files and allow the existing app to refresh. If it still shows the
   previous version, restart/reboot the app.

The other files in this ZIP are documentation, a dependency reference, and a
backup. They can be kept with your project, but only app2627.py and the complete
instruments folder are required for this replacement.

### Keep the existing logo

The attached Python source refers to:

`assets/penn_state_college_of_medicine_logo.png`

The image itself was not included in the attachment, so this ZIP does not
contain a replacement logo. Keep that existing file in your repository at its
current path. The PDF code and its path are preserved.

### Keep your existing settings and saved presenter information

Continue using your existing Streamlit Secrets values for:

| Secrets section | Keys |
|---|---|
| feedback_encryption | key |
| github | token, repo, branch (if configured) |

Keep the **same encryption key** so the app can read your saved presenter and
session information. The code still uses `data/session_feedback_options.enc`
in the configured GitHub repository and retains its existing migration from
`data/session_feedback_options.json` when applicable.

No secret values were included in the attachment or added to this ZIP.

## Which file do I edit?

All ten section files are inside **instruments/**.

| Dropdown in the app | File to edit |
|---|---|
| OASIS Evaluation | instruments/oasis_evaluation.py |
| Checklist Entry | instruments/checklist_entry.py |
| Preceptor Matching | instruments/preceptor_matching.py |
| NBME Scores | instruments/nbme_scores.py |
| Roster_HMC | instruments/roster_hmc.py |
| Roster_KP | instruments/roster_kp.py |
| Roster_Updater | instruments/roster_updater.py |
| Oasis Reminder | instruments/oasis_reminder.py |
| Session Feedback Link Creator | instruments/session_feedback_link_creator.py |
| Session Feedback Summary Creator | instruments/session_feedback_summary_creator.py |

For example:

- Change presenter/session options, saved presenter management, encryption,
  feedback links, QR codes, or the QR PDF in **session_feedback_link_creator.py**.
- Change rating questions, comments, Word reports, or the combined summary CSV
  in **session_feedback_summary_creator.py**.
- Change the dropdown choices or general header in **app2627.py**.

For an existing section, you usually only need to edit and commit that one
section file. Keep its `def render():` function and its existing indentation.
You do not need to paste the section back into app2627.py or add an
`if instrument == ...` line inside it.

Keep the section folder named **instruments** so the main file can find it.

## Dependencies

**Keep the working requirements.txt already in your repository.** No new
third-party package was introduced by this split.

`requirements_reference.txt` lists the packages used by the attached source,
including the Excel-reading dependency. It is a reference file rather than a
replacement for your existing version pins. It is intentionally not named
requirements.txt, so uploading this ZIP's contents will not overwrite your
working dependency file.

For a new installation without an existing dependency file, you can copy that
reference to requirements.txt and configure the same secrets and logo. For a
local run with the dependencies already installed, use:

```bash
python -m streamlit run app2627.py
```

## What is included?

| File or folder | Purpose |
|---|---|
| app2627.py | Main Streamlit app; 64 lines |
| instruments/ | All ten dropdown sections, plus __init__.py |
| README_START_HERE.md | Upload and editing instructions |
| requirements_reference.txt | Existing package requirements, with no guessed version pins |
| VERIFICATION.md | Details of the comparisons performed |
| original_backup/app2627_original.py | Exact copy of the uploaded source for reference or rollback |

## If you need to restore the original

Copy the contents of **original_backup/app2627_original.py** back into your
main **app2627.py**, then commit that change. The backup is an exact copy of the
uploaded `app2627 (1).py`. The original app does not use the instruments folder,
so it can remain present after a rollback.

## Verification scope

The split was compared with this exact uploaded file. Validation used synthetic
inputs, Python source comparisons, Streamlit's testing framework, and simulated
GitHub responses. Live REDCap/OASIS/GitHub accounts and your deployed Streamlit
environment were not accessed. Details are in VERIFICATION.md.
