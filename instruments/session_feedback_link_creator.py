# Session Feedback Link Creator
# Edit this file to change this dropdown section.
# app2627.py calls render() on every Streamlit rerun.
# The original section body is preserved below.

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


def render():
    st.header("📋 Session Feedback Link Creator")

    import io
    import os
    import json
    import base64
    import urllib.parse
    import hashlib
    import requests
    import qrcode

    from cryptography.fernet import Fernet, InvalidToken

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
    LOGO_PATH = "assets/penn_state_college_of_medicine_logo.png"
    
    # ---------------------------------------------------------
    # NEW encrypted file
    # ---------------------------------------------------------

    GITHUB_DATA_FILE = (
        "data/session_feedback_options.enc"
    )

    # ---------------------------------------------------------
    # OLD plaintext file
    #
    # Used only for one-time migration if the encrypted file
    # does not exist yet.
    # ---------------------------------------------------------

    LEGACY_GITHUB_DATA_FILE = (
        "data/session_feedback_options.json"
    )

    OTHER_OPTION = (
        "➕ Other / enter manually"
    )


    # =========================================================
    # DEFAULT DATA
    # =========================================================

    DEFAULT_SESSIONS = {

        "Conrad Krawiec": {

            "username": "czk11",

            "sessions": [
                "Residency Journal Club"
            ]
        }
    }


    # =========================================================
    # STREAMLIT ENCRYPTION KEY
    # =========================================================
    #
    # Streamlit Secrets:
    #
    # [feedback_encryption]
    # key = "YOUR_FERNET_KEY"
    #
    # =========================================================

    try:

        ENCRYPTION_KEY = str(
            st.secrets[
                "feedback_encryption"
            ][
                "key"
            ]
        ).strip()


        cipher = Fernet(
            ENCRYPTION_KEY.encode(
                "utf-8"
            )
        )


    except Exception:

        st.error(
            "Session Feedback encryption is not configured. "
            "Add [feedback_encryption] and its key to "
            "Streamlit Secrets."
        )

        st.stop()


    # =========================================================
    # GITHUB SETTINGS
    # =========================================================
    #
    # Streamlit Secrets:
    #
    # [github]
    # token = "github_pat_..."
    # repo = "username/repository"
    # branch = "main"
    #
    # =========================================================

    try:

        GITHUB_TOKEN = str(
            st.secrets[
                "github"
            ][
                "token"
            ]
        ).strip()


        GITHUB_REPO = str(
            st.secrets[
                "github"
            ][
                "repo"
            ]
        ).strip()


        GITHUB_BRANCH = str(
            st.secrets[
                "github"
            ].get(
                "branch",
                "main"
            )
        ).strip()


        github_configured = True


    except Exception:

        GITHUB_TOKEN = ""
        GITHUB_REPO = ""
        GITHUB_BRANCH = "main"

        github_configured = False


    # =========================================================
    # SMALL HELPER FOR STREAMLIT WIDGET KEYS
    # =========================================================

    def widget_suffix(value):

        return hashlib.sha256(
            str(value).encode(
                "utf-8"
            )
        ).hexdigest()[:12]


    # =========================================================
    # NORMALIZE SAVED DATA
    # =========================================================
    #
    # Supports BOTH:
    #
    # OLD FORMAT:
    #
    # "Conrad Krawiec": [
    #     "Residency Journal Club"
    # ]
    #
    # NEW FORMAT:
    #
    # "Conrad Krawiec": {
    #     "username": "czk11",
    #     "sessions": [
    #         "Residency Journal Club"
    #     ]
    # }
    #
    # =========================================================

    def normalize_saved_sessions(
        data
    ):

        cleaned_sessions = {}


        if not isinstance(
            data,
            dict
        ):

            return cleaned_sessions


        for person, info in (
            data.items()
        ):

            person = str(
                person
            ).strip()


            if not person:

                continue


            # -------------------------------------------------
            # OLD FORMAT
            # -------------------------------------------------

            if isinstance(
                info,
                list
            ):

                cleaned_sessions[
                    person
                ] = {

                    "username": "",

                    "sessions": sorted(
                        {
                            str(title).strip()
                            for title in info
                            if str(title).strip()
                        }
                    )
                }


            # -------------------------------------------------
            # NEW FORMAT
            # -------------------------------------------------

            elif isinstance(
                info,
                dict
            ):

                username_value = str(
                    info.get(
                        "username",
                        ""
                    )
                ).strip()


                titles = info.get(
                    "sessions",
                    []
                )


                if not isinstance(
                    titles,
                    list
                ):

                    titles = [
                        titles
                    ]


                cleaned_titles = sorted(
                    {
                        str(title).strip()
                        for title in titles
                        if str(title).strip()
                    }
                )


                cleaned_sessions[
                    person
                ] = {

                    "username":
                        username_value,

                    "sessions":
                        cleaned_titles
                }


        return cleaned_sessions


    # =========================================================
    # ENCRYPT / DECRYPT
    # =========================================================

    def encrypt_saved_data(
        data
    ):

        # -----------------------------------------------------
        # Normalize before saving
        # -----------------------------------------------------

        data = normalize_saved_sessions(
            data
        )


        # -----------------------------------------------------
        # Convert dictionary to JSON
        # -----------------------------------------------------

        json_text = json.dumps(
            data,
            ensure_ascii=False,
            separators=(
                ",",
                ":"
            )
        )


        # -----------------------------------------------------
        # Encrypt entire JSON document
        # -----------------------------------------------------

        encrypted_bytes = (
            cipher.encrypt(
                json_text.encode(
                    "utf-8"
                )
            )
        )


        return encrypted_bytes.decode(
            "utf-8"
        )


    def decrypt_saved_data(
        encrypted_text
    ):

        # -----------------------------------------------------
        # Decrypt Fernet token
        # -----------------------------------------------------

        decrypted_bytes = (
            cipher.decrypt(
                encrypted_text.encode(
                    "utf-8"
                )
            )
        )


        # -----------------------------------------------------
        # Convert decrypted JSON back to dictionary
        # -----------------------------------------------------

        data = json.loads(
            decrypted_bytes.decode(
                "utf-8"
            )
        )


        return normalize_saved_sessions(
            data
        )


    # =========================================================
    # GITHUB HELPERS
    # =========================================================

    def github_headers():

        return {

            "Authorization":
                f"Bearer {GITHUB_TOKEN}",

            "Accept":
                "application/vnd.github+json",

            "X-GitHub-Api-Version":
                "2022-11-28",
        }


    def github_file_url(
        file_path
    ):

        encoded_path = (
            urllib.parse.quote(
                file_path,
                safe="/"
            )
        )


        return (
            f"https://api.github.com/repos/"
            f"{GITHUB_REPO}/contents/"
            f"{encoded_path}"
        )


    # =========================================================
    # SAVE ENCRYPTED DATA TO GITHUB
    # =========================================================

    def save_saved_sessions(
        data,
        commit_message=(
            "Update encrypted session feedback options"
        )
    ):

        if not github_configured:

            st.error(
                "GitHub persistence is not configured. "
                "Add the [github] section to "
                "Streamlit Secrets."
            )

            return False


        # -----------------------------------------------------
        # Normalize
        # -----------------------------------------------------

        data = normalize_saved_sessions(
            data
        )


        # -----------------------------------------------------
        # Encrypt
        # -----------------------------------------------------

        encrypted_text = (
            encrypt_saved_data(
                data
            )
        )


        # -----------------------------------------------------
        # GitHub Contents API itself requires file content
        # to be base64 encoded.
        #
        # This is separate from the encryption.
        # -----------------------------------------------------

        encoded_content = (
            base64.b64encode(
                encrypted_text.encode(
                    "utf-8"
                )
            )
            .decode(
                "utf-8"
            )
        )


        url = github_file_url(
            GITHUB_DATA_FILE
        )


        sha = None


        try:

            # =================================================
            # CHECK IF ENCRYPTED FILE ALREADY EXISTS
            # =================================================

            current_response = (
                requests.get(
                    url,
                    headers=github_headers(),
                    params={
                        "ref":
                            GITHUB_BRANCH
                    },
                    timeout=15,
                )
            )


            if (
                current_response.status_code
                == 200
            ):

                sha = (
                    current_response
                    .json()
                    .get(
                        "sha"
                    )
                )


            elif (
                current_response.status_code
                != 404
            ):

                st.error(
                    "Could not check the encrypted "
                    "GitHub data file. "
                    f"HTTP "
                    f"{current_response.status_code}"
                )

                return False


            # =================================================
            # GITHUB PAYLOAD
            # =================================================

            payload = {

                "message":
                    commit_message,

                "content":
                    encoded_content,

                "branch":
                    GITHUB_BRANCH,
            }


            # -------------------------------------------------
            # SHA required when updating existing file
            # -------------------------------------------------

            if sha:

                payload[
                    "sha"
                ] = sha


            # =================================================
            # SAVE
            # =================================================

            response = requests.put(
                url,
                headers=github_headers(),
                json=payload,
                timeout=15,
            )


            if response.status_code in (
                200,
                201
            ):

                return True


            st.error(
                "GitHub could not save the encrypted "
                "presenter information. "
                f"HTTP {response.status_code}: "
                f"{response.text}"
            )


            return False


        except Exception as e:

            st.error(
                "Unable to save encrypted "
                f"presenter information: {e}"
            )

            return False


    # =========================================================
    # LOAD OLD PLAINTEXT FILE
    # =========================================================
    #
    # Only used if encrypted .enc file does not exist.
    #
    # =========================================================

    def load_legacy_plaintext_file():

        if not github_configured:

            return None


        legacy_url = github_file_url(
            LEGACY_GITHUB_DATA_FILE
        )


        try:

            response = requests.get(
                legacy_url,
                headers=github_headers(),
                params={
                    "ref":
                        GITHUB_BRANCH
                },
                timeout=15,
            )


            if (
                response.status_code
                == 404
            ):

                return None


            if (
                response.status_code
                != 200
            ):

                return None


            file_info = (
                response.json()
            )


            encoded_content = (
                file_info.get(
                    "content",
                    ""
                )
            )


            decoded_content = (
                base64.b64decode(
                    encoded_content
                )
                .decode(
                    "utf-8"
                )
                .strip()
            )


            if not decoded_content:

                return None


            try:

                data = json.loads(
                    decoded_content
                )

            except json.JSONDecodeError:

                return None


            return normalize_saved_sessions(
                data
            )


        except Exception:

            return None


    # =========================================================
    # LOAD ENCRYPTED DATA FROM GITHUB
    # =========================================================

    def load_saved_sessions():

        # -----------------------------------------------------
        # If GitHub is unavailable, use defaults for this run.
        # They will not persist.
        # -----------------------------------------------------

        if not github_configured:

            return normalize_saved_sessions(
                DEFAULT_SESSIONS
            )


        url = github_file_url(
            GITHUB_DATA_FILE
        )


        try:

            response = requests.get(
                url,
                headers=github_headers(),
                params={
                    "ref":
                        GITHUB_BRANCH
                },
                timeout=15,
            )


            # =================================================
            # ENCRYPTED FILE EXISTS
            # =================================================

            if (
                response.status_code
                == 200
            ):

                file_info = (
                    response.json()
                )


                encoded_content = (
                    file_info.get(
                        "content",
                        ""
                    )
                )


                encrypted_text = (
                    base64.b64decode(
                        encoded_content
                    )
                    .decode(
                        "utf-8"
                    )
                    .strip()
                )


                if not encrypted_text:

                    st.error(
                        "The encrypted presenter file "
                        "exists but is empty."
                    )

                    st.stop()


                try:

                    return decrypt_saved_data(
                        encrypted_text
                    )


                except InvalidToken:

                    st.error(
                        "The encrypted presenter file "
                        "could not be decrypted. "
                        "The Streamlit encryption key "
                        "does not match the key that was "
                        "used to create this file."
                    )

                    st.stop()


                except Exception as e:

                    st.error(
                        "The encrypted presenter file "
                        "could not be read. "
                        f"{e}"
                    )

                    st.stop()


            # =================================================
            # ENCRYPTED FILE DOES NOT EXIST
            # =================================================

            elif (
                response.status_code
                == 404
            ):

                # ---------------------------------------------
                # Check for OLD plaintext JSON
                # ---------------------------------------------

                legacy_data = (
                    load_legacy_plaintext_file()
                )


                if legacy_data:

                    success = (
                        save_saved_sessions(
                            legacy_data,
                            commit_message=(
                                "Migrate session feedback "
                                "options to encrypted storage"
                            )
                        )
                    )


                    if success:

                        st.warning(
                            "Your old presenter data was "
                            "successfully migrated to the "
                            "encrypted GitHub file. "
                            "The old plaintext JSON file "
                            "still exists in GitHub and "
                            "should be removed."
                        )


                    return legacy_data


                # ---------------------------------------------
                # No old file either.
                # Create encrypted defaults.
                # ---------------------------------------------

                default_data = (
                    normalize_saved_sessions(
                        DEFAULT_SESSIONS
                    )
                )


                save_saved_sessions(
                    default_data,
                    commit_message=(
                        "Create encrypted session "
                        "feedback options"
                    )
                )


                return default_data


            # =================================================
            # UNEXPECTED GITHUB ERROR
            # =================================================

            else:

                st.error(
                    "Could not load the encrypted "
                    "presenter information from GitHub. "
                    f"HTTP {response.status_code}"
                )

                st.stop()


        except Exception as e:

            st.error(
                "Could not load encrypted presenter "
                f"information: {e}"
            )

            st.stop()


    # =========================================================
    # LOAD SAVED DATA
    # =========================================================

    saved_sessions = (
        load_saved_sessions()
    )


    # =========================================================
    # SESSION INFORMATION
    # =========================================================

    st.subheader(
        "Session Information"
    )


    # =========================================================
    # PRESENTER DROPDOWN
    # =========================================================

    presenter_options = (

        sorted(
            saved_sessions.keys()
        )

        + [
            OTHER_OPTION
        ]
    )


    selected_presenter = st.selectbox(
        "Presenter",
        options=presenter_options,
        index=None,
        placeholder="Select presenter...",
        key="feedback_presenter_select"
    )


    presenter = ""
    username = ""
    session_title = ""

    manual_presenter = False
    manual_username = False
    manual_title = False


    # =========================================================
    # NEW / MANUAL PRESENTER
    # =========================================================

    if (
        selected_presenter
        == OTHER_OPTION
    ):

        manual_presenter = True
        manual_username = True


        presenter = st.text_input(
            "Presenter name",
            value="",
            placeholder=(
                "Enter presenter name"
            ),
            key=(
                "manual_feedback_presenter"
            )
        )


        username = st.text_input(
            "Username",
            value="",
            placeholder=(
                "Enter presenter username"
            ),
            key=(
                "manual_feedback_username"
            )
        )


    # =========================================================
    # EXISTING PRESENTER
    # =========================================================

    elif selected_presenter:

        presenter = (
            selected_presenter
        )


        presenter_info = (
            saved_sessions.get(
                presenter,
                {
                    "username": "",
                    "sessions": []
                }
            )
        )


        stored_username = str(
            presenter_info.get(
                "username",
                ""
            )
        ).strip()


        # -----------------------------------------------------
        # Username already stored
        # -----------------------------------------------------

        if stored_username:

            username = (
                stored_username
            )


            st.text_input(
                "Username",
                value=username,
                disabled=True,
                key=(
                    "existing_username_"
                    + widget_suffix(
                        presenter
                    )
                )
            )


        # -----------------------------------------------------
        # Old presenter without saved username
        # -----------------------------------------------------

        else:

            manual_username = True


            username = st.text_input(
                "Username",
                value="",
                placeholder=(
                    "Enter presenter username"
                ),
                key=(
                    "missing_username_"
                    + widget_suffix(
                        presenter
                    )
                )
            )


    # =========================================================
    # SESSION TITLE
    # =========================================================

    if presenter:

        # -----------------------------------------------------
        # EXISTING PRESENTER
        # -----------------------------------------------------

        if (
            presenter
            in saved_sessions
        ):

            presenter_sessions = (
                saved_sessions[
                    presenter
                ].get(
                    "sessions",
                    []
                )
            )


            title_options = (

                sorted(
                    presenter_sessions
                )

                + [
                    OTHER_OPTION
                ]
            )


            selected_title = st.selectbox(
                "Session Title",
                options=title_options,
                index=None,
                placeholder=(
                    "Select session title..."
                ),
                key=(
                    "feedback_title_"
                    + widget_suffix(
                        presenter
                    )
                )
            )


            # -------------------------------------------------
            # Add new title
            # -------------------------------------------------

            if (
                selected_title
                == OTHER_OPTION
            ):

                manual_title = True


                session_title = (
                    st.text_input(
                        "Session title",
                        value="",
                        placeholder=(
                            "Enter session title"
                        ),
                        key=(
                            "manual_title_"
                            + widget_suffix(
                                presenter
                            )
                        )
                    )
                )


            elif selected_title:

                session_title = (
                    selected_title
                )


        # -----------------------------------------------------
        # BRAND NEW PRESENTER
        # -----------------------------------------------------

        else:

            manual_title = True


            session_title = (
                st.text_input(
                    "Session Title",
                    value="",
                    placeholder=(
                        "Enter session title"
                    ),
                    key=(
                        "new_presenter_"
                        "session_title"
                    )
                )
            )


    # =========================================================
    # NO PRESENTER SELECTED
    # =========================================================

    else:

        st.selectbox(
            "Session Title",
            options=[],
            index=None,
            placeholder=(
                "Select a presenter first..."
            ),
            disabled=True,
            key=(
                "disabled_feedback_"
                "session_title"
            )
        )


    # =========================================================
    # DATE
    # =========================================================

    session_date = st.date_input(
        "Session Date",
        value=None,
        format="MM/DD/YYYY",
        key="feedback_session_date"
    )


    # ---------------------------------------------------------
    # REDCap requires YYYY-MM-DD for URL prefill
    # ---------------------------------------------------------

    date_for_redcap = (

        session_date.strftime(
            "%Y-%m-%d"
        )

        if session_date

        else ""
    )


    # ---------------------------------------------------------
    # Friendly date shown on PDF
    # ---------------------------------------------------------

    session_date_display = (

        session_date.strftime(
            "%m/%d/%Y"
        )

        if session_date

        else ""
    )


    # =========================================================
    # SAVE NEW PRESENTER / USERNAME / SESSION
    # =========================================================

    if (
        username.strip()
        and presenter.strip()
        and session_title.strip()
        and (
            manual_presenter
            or manual_username
            or manual_title
        )
    ):

        if st.button(
            "💾 Save Presenter / Session for Future Use",
            use_container_width=True,
            key=(
                "save_feedback_"
                "presenter_session"
            )
        ):

            presenter_clean = (
                presenter.strip()
            )

            username_clean = (
                username.strip()
            )

            title_clean = (
                session_title.strip()
            )


            # -------------------------------------------------
            # Get latest encrypted copy from GitHub
            # -------------------------------------------------

            latest_sessions = (
                load_saved_sessions()
            )


            # -------------------------------------------------
            # Create presenter if necessary
            # -------------------------------------------------

            if (
                presenter_clean
                not in latest_sessions
            ):

                latest_sessions[
                    presenter_clean
                ] = {

                    "username":
                        username_clean,

                    "sessions":
                        []
                }


            presenter_entry = (
                latest_sessions[
                    presenter_clean
                ]
            )


            if not isinstance(
                presenter_entry,
                dict
            ):

                presenter_entry = {

                    "username":
                        username_clean,

                    "sessions":
                        []
                }


            # -------------------------------------------------
            # Save username
            # -------------------------------------------------

            presenter_entry[
                "username"
            ] = username_clean


            # -------------------------------------------------
            # Save session title
            # -------------------------------------------------

            existing_titles = (
                presenter_entry.get(
                    "sessions",
                    []
                )
            )


            if not isinstance(
                existing_titles,
                list
            ):

                existing_titles = []


            if (
                title_clean
                not in existing_titles
            ):

                existing_titles.append(
                    title_clean
                )


            presenter_entry[
                "sessions"
            ] = sorted(
                set(
                    existing_titles
                )
            )


            latest_sessions[
                presenter_clean
            ] = presenter_entry


            # -------------------------------------------------
            # Encrypt and save to GitHub
            # -------------------------------------------------

            success = (
                save_saved_sessions(
                    latest_sessions,
                    commit_message=(
                        "Update encrypted session "
                        "feedback option"
                    )
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

    if (
        username.strip()
        and presenter.strip()
        and session_title.strip()
    ):

        params = {

            "username":
                username.strip(),

            "presenter":
                presenter.strip(),

            "title":
                session_title.strip(),
        }


        if date_for_redcap:

            params[
                "date"
            ] = date_for_redcap


        encoded_params = (
            urllib.parse.urlencode(
                params
            )
        )


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
                qrcode.constants
                .ERROR_CORRECT_M
            ),

            box_size=10,

            border=4,
        )


        qr.add_data(
            feedback_url
        )

        qr.make(
            fit=True
        )


        qr_image = qr.make_image(
            fill_color="black",
            back_color="white"
        )


        qr_buffer = io.BytesIO()


        qr_image.save(
            qr_buffer,
            format="PNG"
        )


        qr_buffer.seek(
            0
        )


        qr_bytes = (
            qr_buffer.getvalue()
        )


        # =====================================================
        # DISPLAY LINK + QR
        # =====================================================

        st.divider()

        st.subheader(
            "Student Feedback Link"
        )


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
        
        
            # =====================================================
            # PENN STATE COLLEGE OF MEDICINE LOGO
            # =====================================================
        
            if os.path.exists(LOGO_PATH):
        
                try:
        
                    logo_reader = ImageReader(
                        LOGO_PATH
                    )
        
                    logo_width = 250
                    logo_height = 60
        
                    c.drawImage(
                        logo_reader,
                        (page_width - logo_width) / 2,
                        page_height - 95,
                        width=logo_width,
                        height=logo_height,
                        preserveAspectRatio=True,
                        mask="auto"
                    )
        
                except Exception:
                    pass
        
        
            # =====================================================
            # TITLE
            # =====================================================
        
            c.setFont(
                "Helvetica-Bold",
                22
            )
        
            c.drawCentredString(
                page_width / 2,
                page_height - 135,
                "Session Feedback"
            )
        
        
            # =====================================================
            # SESSION TITLE
            # =====================================================
        
            c.setFont(
                "Helvetica-Bold",
                16
            )
        
            c.drawCentredString(
                page_width / 2,
                page_height - 170,
                session_title
            )
        
        
            # =====================================================
            # PRESENTER
            # =====================================================
        
            c.setFont(
                "Helvetica",
                13
            )
        
            c.drawCentredString(
                page_width / 2,
                page_height - 195,
                presenter
            )
        
        
            # =====================================================
            # DATE
            # =====================================================
        
            if session_date.strip():
        
                c.setFont(
                    "Helvetica",
                    12
                )
        
                c.drawCentredString(
                    page_width / 2,
                    page_height - 217,
                    session_date
                )
        
        
            # =====================================================
            # INSTRUCTIONS
            # =====================================================
        
            c.setFont(
                "Helvetica",
                13
            )
        
            c.drawCentredString(
                page_width / 2,
                page_height - 255,
                "Please scan the QR code to provide feedback."
            )
        
        
            # =====================================================
            # QR CODE
            # =====================================================
        
            qr_stream = io.BytesIO(
                qr_bytes
            )
        
            qr_reader = ImageReader(
                qr_stream
            )
        
            qr_size = 250
        
            c.drawImage(
                qr_reader,
                (page_width - qr_size) / 2,
                page_height - 540,
                width=qr_size,
                height=qr_size,
                preserveAspectRatio=True
            )
        
        
            # =====================================================
            # CLICKABLE LINK
            # =====================================================
        
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
                page_width
                - link_width
            ) / 2
        
            link_y = (
                page_height
                - 575
            )
        
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
        
        
            # =====================================================
            # FINISH PDF
            # =====================================================
        
            c.save()
        
            pdf_buffer.seek(
                0
            )
        
            return pdf_buffer.getvalue()


        # =====================================================
        # GENERATE PDF
        # =====================================================

        pdf_bytes = (
            create_feedback_pdf(
                presenter,
                session_title,
                session_date_display,
                feedback_url,
                qr_bytes
            )
        )


        # =====================================================
        # DOWNLOAD PDF
        # =====================================================

        st.download_button(
            "📄 Download Feedback QR PDF",
            data=pdf_bytes,
            file_name=(
                "session_feedback_qr.pdf"
            ),
            mime="application/pdf",
            use_container_width=True
        )


    # =========================================================
    # INCOMPLETE INFORMATION
    # =========================================================

    else:

        missing_items = []


        if not presenter.strip():

            missing_items.append(
                "presenter"
            )


        if not username.strip():

            missing_items.append(
                "username"
            )


        if not session_title.strip():

            missing_items.append(
                "session title"
            )


        if missing_items:

            st.info(
                "Complete the "
                + ", ".join(
                    missing_items
                )
                + " to create the feedback link."
            )


    # =========================================================
    # MANAGE SAVED PRESENTERS & SESSIONS
    # =========================================================

    with st.expander(
        "⚙️ Manage Saved Presenters & Sessions"
    ):

        if not github_configured:

            st.warning(
                "GitHub persistence is not configured. "
                "Add the [github] section to "
                "Streamlit Secrets."
            )


        elif not saved_sessions:

            st.info(
                "There are currently "
                "no saved presenters."
            )


        else:

            st.write(
                "Update a username, remove "
                "a saved session title, "
                "or remove a presenter."
            )


            # =================================================
            # SELECT PRESENTER
            # =================================================

            manage_presenter = st.selectbox(
                "Presenter to manage",
                options=sorted(
                    saved_sessions.keys()
                ),
                index=None,
                placeholder=(
                    "Select presenter..."
                ),
                key=(
                    "manage_feedback_presenter"
                )
            )


            if manage_presenter:

                manage_info = (
                    saved_sessions.get(
                        manage_presenter,
                        {
                            "username": "",
                            "sessions": []
                        }
                    )
                )


                manage_suffix = (
                    widget_suffix(
                        manage_presenter
                    )
                )


                # =================================================
                # UPDATE USERNAME
                # =================================================

                st.markdown(
                    "#### Username"
                )


                current_username = str(
                    manage_info.get(
                        "username",
                        ""
                    )
                ).strip()


                updated_username = (
                    st.text_input(
                        "Username",
                        value=current_username,
                        key=(
                            "manage_username_"
                            + manage_suffix
                        )
                    )
                )


                if (
                    updated_username.strip()
                    != current_username
                ):

                    if st.button(
                        "💾 Update Username",
                        use_container_width=True,
                        key=(
                            "update_username_"
                            + manage_suffix
                        )
                    ):

                        if not (
                            updated_username.strip()
                        ):

                            st.warning(
                                "Username cannot be blank."
                            )


                        else:

                            latest_sessions = (
                                load_saved_sessions()
                            )


                            if (
                                manage_presenter
                                in latest_sessions
                            ):

                                latest_sessions[
                                    manage_presenter
                                ][
                                    "username"
                                ] = (
                                    updated_username
                                    .strip()
                                )


                                success = (
                                    save_saved_sessions(
                                        latest_sessions,
                                        commit_message=(
                                            "Update encrypted "
                                            "presenter username"
                                        )
                                    )
                                )


                                if success:

                                    st.success(
                                        "Username updated."
                                    )

                                    st.rerun()


                # =================================================
                # REMOVE INDIVIDUAL SESSION
                # =================================================

                st.divider()

                st.markdown(
                    "#### Saved Sessions"
                )


                presenter_titles = (
                    manage_info.get(
                        "sessions",
                        []
                    )
                )


                if presenter_titles:

                    remove_title = (
                        st.selectbox(
                            "Session title to remove",
                            options=(
                                presenter_titles
                            ),
                            index=None,
                            placeholder=(
                                "Select session title..."
                            ),
                            key=(
                                "remove_title_"
                                + manage_suffix
                            )
                        )
                    )


                    if remove_title:

                        if st.button(
                            "🗑️ Remove This Session",
                            use_container_width=True,
                            key=(
                                "remove_session_"
                                + manage_suffix
                            )
                        ):

                            latest_sessions = (
                                load_saved_sessions()
                            )


                            if (
                                manage_presenter
                                in latest_sessions
                            ):

                                existing_titles = (
                                    latest_sessions[
                                        manage_presenter
                                    ].get(
                                        "sessions",
                                        []
                                    )
                                )


                                latest_sessions[
                                    manage_presenter
                                ][
                                    "sessions"
                                ] = [

                                    title

                                    for title
                                    in existing_titles

                                    if (
                                        title
                                        != remove_title
                                    )
                                ]


                                success = (
                                    save_saved_sessions(
                                        latest_sessions,
                                        commit_message=(
                                            "Remove encrypted "
                                            "session feedback option"
                                        )
                                    )
                                )


                                if success:

                                    st.success(
                                        "Session removed."
                                    )

                                    st.rerun()


                else:

                    st.caption(
                        "This presenter has no "
                        "saved session titles."
                    )


                # =================================================
                # REMOVE ENTIRE PRESENTER
                # =================================================

                st.divider()

                st.markdown(
                    "#### Remove Presenter"
                )


                confirm_remove = (
                    st.checkbox(
                        (
                            f"Remove {manage_presenter} "
                            "and all saved information"
                        ),
                        key=(
                            "confirm_remove_"
                            + manage_suffix
                        )
                    )
                )


                if confirm_remove:

                    if st.button(
                        "🗑️ Remove Presenter",
                        type="primary",
                        use_container_width=True,
                        key=(
                            "remove_presenter_"
                            + manage_suffix
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


                            success = (
                                save_saved_sessions(
                                    latest_sessions,
                                    commit_message=(
                                        "Remove encrypted "
                                        "session feedback presenter"
                                    )
                                )
                            )


                            if success:

                                st.success(
                                    f"{manage_presenter} removed."
                                )

                                st.rerun()
                                

