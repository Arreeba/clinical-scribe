import io
import wave
from datetime import datetime

import streamlit as st

import api
from style import badge_html, blur_css, flag_html, line_html, steps_html

st.set_page_config(page_title="Clinical Scribe", page_icon="🩺", layout="wide")

SECTIONS = (("complaint", "Complaint"), ("history", "History"),
            ("assessment", "Assessment"), ("plan", "Plan"))

STATUS_WORDS = {"draft": "Draft", "edited": "Edited", "approved": "Approved"}

CONSENT_TEXT = ("This consultation will be recorded and transcribed by an AI tool, "
                "and a note will be drafted for your doctor to review. Do you agree?")

# None = the transcript and the note grow with their content.
# A number (for example 560) makes each pane a scrolling box of that height.
PANE_HEIGHT = None

# Streamlit re-runs this whole file on every click, so anything that must
# survive a click is kept in session_state.
DEFAULTS = {"token": None, "doctor": None, "selected": None, "consultations": None,
            "data": None, "notice": None, "highlight": None, "consent_prompt": None,
            "table_nonce": 0, "audit": None, "versions": None,
            "signup": None, "signup_done": None}
for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


def fetch(func, *args):
    # Calls the server with the doctor's token. An expired token logs the doctor out.
    data, error, status = func(st.session_state.token, *args)
    if status == 401:
        st.session_state.clear()
        st.session_state["notice"] = "Your session expired. Please log in again."
        st.rerun()
    return data, error


def refresh_list():
    data, error = fetch(api.list_consultations)
    st.session_state.consultations = data or []
    if error:
        st.sidebar.error(error)


def load_consultation(consultation_id):
    transcript, _ = fetch(api.get_transcript, consultation_id)
    note, _ = fetch(api.get_note, consultation_id)   # a missing note is normal before the audio
    summary = None
    if note and note["status"] == "approved":
        summary, _ = fetch(api.get_summary, consultation_id)   # a 404 just means none yet
    st.session_state.data = {"id": consultation_id, "transcript": transcript or [],
                             "note": note, "summary": summary}
    st.session_state.audit = None
    st.session_state.versions = None


def reload(consultation_id):
    refresh_list()
    load_consultation(consultation_id)


def select(consultation_id):
    st.session_state.selected = consultation_id
    st.session_state.highlight = None
    st.session_state.consent_prompt = consultation_id   # opens the consent popup if needed
    st.session_state.table_nonce += 1                   # the table forgets its selected row
    load_consultation(consultation_id)


def set_highlight(consultation_id, lines, base=None):
    # Runs when "Show source" is clicked, before the page is redrawn
    st.session_state.highlight = {"id": consultation_id, "lines": list(lines), "base": base}


def saved_note(note):
    # The note as the server has it, reduced to the fields the doctor can change
    return {
        key: [{"text": s["text"].strip(), "source_lines": s["source_lines"],
               "needs_review": s["needs_review"], "review_reason": s["review_reason"]}
              for s in note["note"][key]]
        for key, _ in SECTIONS
    }


def edited_note(note, consultation_id):
    # The note as it looks right now in the text boxes and Reviewed ticks
    version = note["version"]
    result = {}
    for key, _ in SECTIONS:
        statements = []
        for i, item in enumerate(note["note"][key]):
            base = f"{consultation_id}_{version}_{key}_{i}"
            text = st.session_state.get(f"text_{base}", item["text"]).strip()
            reviewed = st.session_state.get(f"rev_{base}", False)
            if not text:
                text = item["text"]   # an empty box keeps the saved wording
            if item["needs_review"] and reviewed:
                flag, reason = False, ""
            else:
                flag, reason = item["needs_review"], item["review_reason"]
            statements.append({"text": text, "source_lines": item["source_lines"],
                               "needs_review": flag, "review_reason": reason})
        result[key] = statements
    return result


def pretty_date(iso):
    # "2026-11-16T19:08:30" -> "16 Nov 2026"
    try:
        return datetime.fromisoformat(iso[:19]).strftime("%d %b %Y")
    except ValueError:
        return iso[:10]


def pane():
    # A bordered card for the transcript or the note
    if PANE_HEIGHT is None:
        return st.container(border=True)
    return st.container(height=PANE_HEIGHT, border=True)


def show_length(clip):
    # Shows how long a recorded clip is, and warns if it is long
    if clip is None:
        return
    try:
        with wave.open(io.BytesIO(clip.getvalue())) as w:
            seconds = w.getnframes() / w.getframerate()
    except Exception:
        return
    st.caption(f"Recorded: {seconds:.0f} seconds")
    if seconds > 45:
        st.warning("This clip is long. Shorter clips (about 15 to 20 seconds) work better.")


def show_summary(text):
    # The summary is plain text: blocks separated by blank lines. A block is a heading line,
    # then bullets ("- ...") and plain paragraphs.
    for block in text.split("\n\n"):
        lines = [line.replace("$", "\\$") for line in block.split("\n")]
        if len(lines) > 1 and not lines[0].startswith("- "):
            st.markdown(f"**{lines[0]}**")
            lines = lines[1:]
        pending = []
        for line in lines:
            if line.startswith("- "):
                pending.append(line)
            else:
                if pending:
                    st.markdown("\n".join(pending))
                    pending = []
                st.markdown(line)
        if pending:
            st.markdown("\n".join(pending))


def show_correction(selected, line, n, corr, approved, dirty):
    # Under a transcript line: what the agent did about a medicine name
    status = corr.get("status")
    if corr.get("confirmed"):
        how = ("applied automatically from a saved fix" if status == "auto_applied"
               else "confirmed by the doctor")
        st.caption(f'Medicine name: Whisper heard "{corr["original"]}", '
                   f'corrected to "{corr["confirmed"]}" ({how}).')
        return
    if status != "unreviewed":
        return
    if approved:
        st.caption(f'Medicine name "{corr["original"]}" was never confirmed.')
        return

    base = f"{selected}_{line['line_no']}_{n}"
    with st.container(border=True):
        st.caption(f'Medicine check: Whisper wrote "{corr["original"]}". Which name is correct?')
        names = [c[0] for c in corr.get("candidates", [])]
        other = "Other (type the correct name)"
        choice = st.radio("Suggestions", names + [other], key=f"choice_{base}",
                          label_visibility="collapsed")
        typed = ""
        if choice == other:
            typed = st.text_input("Correct name", key=f"typed_{base}")
        if dirty:
            st.caption("Save your note edits first, then confirm the name.")
        if st.button("Confirm name", key=f"confirm_{base}", disabled=dirty):
            confirmed = typed.strip() if choice == other else choice
            if not confirmed:
                st.error("Type the correct name first.")
            else:
                _, error = fetch(api.confirm_correction, selected, line["line_no"],
                                 corr["original"], confirmed)
                if error:
                    st.error(error)
                else:
                    reload(selected)
                    st.rerun()


def show_history():
    # Note versions and the audit log, loaded only when asked for
    with st.expander("History: note versions and audit log"):
        v_col, a_col = st.columns(2)

        with v_col:
            if st.button("Show note versions"):
                rows, error = fetch(api.get_versions, st.session_state.selected)
                if error:
                    st.error(error)
                else:
                    st.session_state.versions = {"id": st.session_state.selected, "rows": rows}
            v = st.session_state.versions
            if v and v["id"] == st.session_state.selected:
                st.dataframe(
                    [{"Version": r["version"], "Reason": r["reason"],
                      "Saved by": "AI" if r["saved_by"] is None else f'doctor {r["saved_by"]}',
                      "Time (UTC)": r["created_at"][:19].replace("T", " ")} for r in v["rows"]],
                    hide_index=True,
                )

        with a_col:
            if st.button("Show audit log"):
                rows, error = fetch(api.get_audit, st.session_state.selected)
                if error:
                    st.error(error)
                else:
                    st.session_state.audit = {"id": st.session_state.selected, "rows": rows}
            a = st.session_state.audit
            if a and a["id"] == st.session_state.selected:
                st.dataframe(
                    [{"Time (UTC)": r["time"][:19].replace("T", " "), "Action": r["action"],
                      "Detail": r["detail"],
                      "Doctor": "" if r["doctor_id"] is None else r["doctor_id"]} for r in a["rows"]],
                    hide_index=True,
                )


@st.dialog("Patient consent")
def consent_dialog(consultation_id):
    # Fallback for a consultation that exists but has no consent yet
    st.markdown("**Please read this to the patient:**")
    st.info(CONSENT_TEXT)
    agreed = st.checkbox("The patient has agreed", key=f"agree{consultation_id}")
    if st.button("Record consent", type="primary", disabled=not agreed):
        _, error = fetch(api.record_consent, consultation_id)
        if error:
            st.error(error)
        else:
            refresh_list()
            st.rerun()


@st.dialog("New consultation")
def new_consultation_dialog():
    with st.form("new_consultation_form"):
        name = st.text_input("Patient name (fictional)")
        st.markdown("**Please read this to the patient:**")
        st.info(CONSENT_TEXT)
        agreed = st.checkbox("The patient has agreed")
        submitted = st.form_submit_button("Create and record consent", type="primary")
    if submitted:
        if not name.strip():
            st.error("Enter the patient's name.")
        elif not agreed:
            st.error("Consent is required. Tick the box once the patient has agreed.")
        else:
            with st.spinner("Creating the consultation..."):
                new, error = fetch(api.create_consultation, name.strip())
                if not error:
                    fetch(api.record_consent, new["id"])   # if this fails, the consent popup opens on the next page
                    refresh_list()
                    select(new["id"])
            if error:
                st.error(error)
            else:
                st.rerun()


def show_home():
    # The home page: a searchable table of this doctor's consultations
    consultations = st.session_state.consultations or []
    approved_count = sum(1 for c in consultations if c["status"] == "approved")
    open_count = len(consultations) - approved_count

    title_col, button_col = st.columns([4, 1])
    with title_col:
        st.header("My consultations")
        st.caption(f"{open_count} open  ·  {approved_count} approved")
    with button_col:
        st.write("")
        if st.button("+ New consultation", type="primary"):
            st.markdown(blur_css(), unsafe_allow_html=True)
            new_consultation_dialog()

    search = st.text_input("Search", placeholder="Search by patient name",
                           label_visibility="collapsed")
    rows = [c for c in consultations if search.strip().lower() in c["patient_name"].lower()]
    rows.sort(key=lambda c: c["id"], reverse=True)

    if not consultations:
        st.info("No consultations yet. Click + New consultation to start.")
        return
    if not rows:
        st.info(f'No consultations match "{search}".')
        return

    table = [{"Patient": c["patient_name"], "No.": f'#{c["id"]}',
              "Date": pretty_date(c["created_at"]),
              "Status": STATUS_WORDS.get(c["status"], c["status"])} for c in rows]
    event = st.dataframe(table, hide_index=True, on_select="rerun",
                         selection_mode="single-row",
                         key=f"consultation_table_{st.session_state.table_nonce}")
    picked = event.selection.rows
    if picked:
        with st.spinner("Opening consultation..."):
            select(rows[picked[0]]["id"])
        st.rerun()
    st.caption("Tick the box at the left of a row to open that consultation.")


def show_signup():
    # Sign-up: Google confirms the email, the server checks the registry, then a username and password
    st.subheader("Create your account")
    st.caption("Sign-up is open to doctors on the clinic's registry. Google confirms your email, "
               "then you choose a username and password.")

    if not st.user.is_logged_in:
        st.button("Sign up with Google", type="primary", on_click=st.login)
        return

    # The account was just created: show the result and end the Google session
    if st.session_state.signup_done:
        st.success(f"Account created. Your username is **{st.session_state.signup_done}**. "
                   "You can log in with it, or with your email.")
        st.button("Go to log in", type="primary", on_click=st.logout)
        return

    email = str(st.user.email or "").strip().lower()
    verified = bool(getattr(st.user, "email_verified", False))

    # Ask the server once per email, so the audit log is not filled with repeats
    state = st.session_state.signup
    if state is None or state["email"] != email:
        with st.spinner("Checking the clinic registry..."):
            info, error, _ = api.signup_check(email, verified)
        state = {"email": email, "info": info, "error": error}
        st.session_state.signup = state

    st.caption(f"Signed in with Google as {email}")
    if state["error"]:
        st.error(state["error"])
        st.button("Use a different Google account", on_click=st.logout)
        return

    st.success(f'Welcome, {state["info"]["full_name"]} ({state["info"]["specialty"]}). '
               "Choose a username and a password.")
    with st.form("signup_form"):
        username = st.text_input("Username", help="3 to 30 characters: lowercase letters, digits or underscores, starting with a letter")
        password = st.text_input("Password", type="password", help="8 to 72 characters")
        again = st.text_input("Repeat the password", type="password")
        submitted = st.form_submit_button("Create account", type="primary")
    if submitted:
        if password != again:
            st.error("The two passwords do not match.")
        else:
            data, error, _ = api.signup_complete(email, verified, username.strip(), password)
            if error:
                st.error(error)
            else:
                st.session_state.signup_done = data["username"]
                st.rerun()
    st.button("Cancel and sign out of Google", on_click=st.logout)


# ---------- Login page ----------
if st.session_state.token is None:
    _, middle, _ = st.columns([1, 2, 1])
    with middle:
        st.title("Clinical Scribe")
        st.caption("Consultation notes drafted for your review. Fictional demonstration data only.")
        if st.session_state.notice:
            st.warning(st.session_state.notice)

        # After Google sends the doctor back, the page opens on "Sign up" by itself
        mode = st.radio("Choose", ["Log in", "Sign up"], horizontal=True,
                        index=1 if st.user.is_logged_in else 0,
                        label_visibility="collapsed")
        if mode == "Log in":
            with st.form("login"):
                username = st.text_input("Username or email")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Log in", type="primary")
            if submitted:
                with st.spinner("Logging in..."):
                    data, error, _ = api.login(username, password)
                    if not error:
                        st.session_state.token = data["access_token"]
                        st.session_state.doctor = username
                        st.session_state.notice = None
                        refresh_list()
                if error:
                    st.error(error)
                else:
                    st.rerun()
        else:
            show_signup()
    st.stop()

# ---------- Sidebar ----------
with st.sidebar:
    st.subheader("Clinical Scribe")
    st.caption(f"Signed in as {st.session_state.doctor}")
    if st.button("Log out"):
        st.session_state.clear()
        st.rerun()
    st.divider()
    if st.button("My consultations"):
        st.session_state.selected = None
        st.session_state.highlight = None
        st.rerun()
    st.divider()
    st.caption("Fictional demonstration data only.")

if st.session_state.consultations is None:
    refresh_list()

# ---------- Home page ----------
selected = st.session_state.selected
if selected is None:
    show_home()
    st.stop()

# ---------- A consultation ----------
current = next((c for c in st.session_state.consultations if c["id"] == selected), None)
if current is None:
    st.warning("That consultation was not found.")
    st.stop()

if st.session_state.data is None or st.session_state.data["id"] != selected:
    load_consultation(selected)
data = st.session_state.data
note = data["note"]
has_transcript = bool(data["transcript"])
approved = current["status"] == "approved"

if note is not None:
    dirty = edited_note(note, selected) != saved_note(note)   # unsaved changes?
    flagged_open = sum(1 for key, _ in SECTIONS for s in edited_note(note, selected)[key]
                       if s["needs_review"])
else:
    dirty, flagged_open = False, 0

# Which step the doctor is on
if not current["consent_given"]:
    step = 0
elif not has_transcript or note is None:
    step = 1
elif approved:
    step = 5 if data.get("summary") else 4
elif flagged_open:
    step = 2
else:
    step = 3

if st.button("← Back to my consultations"):
    st.session_state.selected = None
    st.session_state.highlight = None
    st.rerun()

with st.container(border=True):
    name_col, meta_col, badge_col = st.columns([3, 3, 1])
    with name_col:
        st.subheader(current["patient_name"])
    with meta_col:
        st.caption(f'Consultation #{selected}  ·  {pretty_date(current["created_at"])}  ·  '
                   f'{st.session_state.doctor}')
    with badge_col:
        st.markdown(badge_html(current["status"]), unsafe_allow_html=True)
st.markdown(steps_html(step), unsafe_allow_html=True)

# ---------- Step 1: consent (a popup) ----------
if not current["consent_given"]:
    st.warning("The patient's consent has not been recorded. Recording is disabled until it is.")
    clicked = st.button("Record patient consent", type="primary")
    if clicked or st.session_state.consent_prompt == selected:
        st.session_state.consent_prompt = None
        st.markdown(blur_css(), unsafe_allow_html=True)
        consent_dialog(selected)
    st.stop()

# ---------- Step 2: record ----------
if not has_transcript:
    st.subheader("Record the consultation")
    mode = st.radio("How do you want to add the two clips?",
                    ["Record with the microphone", "Upload audio files"],
                    horizontal=True, key=f"mode{selected}")
    doc_col, pat_col = st.columns(2)

    if mode == "Record with the microphone":
        st.caption("Record the doctor's part first, then the patient's part. Click the microphone "
                   "to start and click again to stop. Keep each clip short, about 15 to 20 seconds, "
                   "and pause briefly after each sentence.")
        with doc_col:
            with st.container(border=True):
                st.markdown("**Doctor's part**")
                doctor_file = st.audio_input("Doctor's part", key=f"micdoc{selected}",
                                             label_visibility="collapsed")
                show_length(doctor_file)
        with pat_col:
            with st.container(border=True):
                st.markdown("**Patient's part**")
                patient_file = st.audio_input("Patient's part", key=f"micpat{selected}",
                                              label_visibility="collapsed")
                show_length(patient_file)
    else:
        kinds = ["m4a", "wav", "mp3", "ogg", "webm", "mp4"]
        with doc_col:
            with st.container(border=True):
                st.markdown("**Doctor's clip**")
                doctor_file = st.file_uploader("Doctor's clip", type=kinds, key=f"doctor{selected}",
                                               label_visibility="collapsed")
        with pat_col:
            with st.container(border=True):
                st.markdown("**Patient's clip**")
                patient_file = st.file_uploader("Patient's clip", type=kinds, key=f"patient{selected}",
                                                label_visibility="collapsed")

    ready = doctor_file is not None and patient_file is not None
    if st.button("Generate note", type="primary", disabled=not ready):
        with st.spinner("Transcribing and writing the note. This can take 1 to 2 minutes, "
                        "especially the first time. Please don't click anything meanwhile..."):
            _, error = fetch(api.upload_audio, selected, doctor_file, patient_file)
        if error:
            st.error(error)
        else:
            reload(selected)
            st.rerun()
    st.stop()

if note is None:
    st.info("There is a transcript but no note yet.")
    st.stop()

version = note["version"]

# ---------- Approved: the note and the patient summary ----------
if approved:
    st.success("This note is approved and locked. It cannot be changed.")
    note_col, summary_col = st.columns(2)

    with note_col:
        with st.container(border=True):
            st.subheader("Approved note")
            st.caption(f"Version {version}. Locked.")
            for key, title in SECTIONS:
                st.markdown(f"**{title}**")
                statements = note["note"][key]
                if not statements:
                    st.caption("None recorded.")
                for item in statements:
                    st.markdown("- " + item["text"].replace("$", "\\$"))

    with summary_col:
        with st.container(border=True):
            st.subheader("Patient summary")
            summary = data.get("summary")
            if summary is None:
                st.caption("The summary is written from the approved note only.")
                if st.button("Create patient summary", type="primary"):
                    with st.spinner("Writing the summary. This takes a few seconds..."):
                        _, error = fetch(api.create_summary, selected)
                    if error:
                        st.error(error)
                    else:
                        reload(selected)
                        st.rerun()
            else:
                show_summary(summary["text"])
                st.divider()
                token, consultation_id = st.session_state.token, selected

                def make_pdf():
                    # Runs when the doctor clicks the button, so the export is logged then
                    content, error, _ = api.get_pdf(token, consultation_id)
                    if error:
                        raise RuntimeError(error)
                    return content

                st.download_button("Download PDF", data=make_pdf,
                                   file_name=f"visit_summary_{selected}.pdf",
                                   mime="application/pdf", type="primary", on_click="ignore")

    with st.expander("Show the transcript"):
        for line in data["transcript"]:
            st.markdown(
                line_html(line["line_no"], line["speaker"], line["text"], False, line.get("low_words", [])),
                unsafe_allow_html=True,
            )
            for n, corr in enumerate(line["corrections"]):
                show_correction(selected, line, n, corr, True, False)

    show_history()
    st.stop()

# ---------- Review: the action bar, then the transcript and the note ----------
with st.container(border=True):
    msg_col, save_col, approve_col = st.columns([4, 1.2, 1.8])
    with msg_col:
        if flagged_open:
            st.markdown(f"**Next step:** check the {flagged_open} highlighted item(s) and tick "
                        "**Reviewed** on each one.")
        else:
            st.markdown("**Next step:** everything is checked. Press **Save and approve** when ready.")
        if dirty:
            st.caption("You have unsaved changes.")
    with save_col:
        save_clicked = st.button("Save draft", disabled=not dirty)
    with approve_col:
        approve_clicked = st.button("Save and approve", type="primary", disabled=flagged_open > 0)

if save_clicked or approve_clicked:
    error = None
    if dirty:
        with st.spinner("Saving your edits..."):
            _, error = fetch(api.edit_note, selected, edited_note(note, selected))
    if not error and approve_clicked:
        with st.spinner("Approving the note..."):
            _, error = fetch(api.approve_note, selected)
        if not error:
            st.session_state.highlight = None   # the highlight is not needed after approval
            with st.spinner("Note approved. Writing the patient summary..."):
                fetch(api.create_summary, selected)   # if it fails, the Create button is still there
    if error:
        st.error(error)
    else:
        with st.spinner("Updating the page..."):
            reload(selected)
        st.rerun()

hl = st.session_state.highlight
highlighted = set(hl["lines"]) if hl and hl["id"] == selected else set()
lines_by_no = {l["line_no"]: l for l in data["transcript"]}

left, right = st.columns(2)

with left:
    st.subheader("Transcript")
    st.caption("A wavy red underline marks a word Whisper was unsure of. Hover over it to see the score.")
    with pane():
        for line in data["transcript"]:
            st.markdown(
                line_html(line["line_no"], line["speaker"], line["text"],
                          line["line_no"] in highlighted, line.get("low_words", [])),
                unsafe_allow_html=True,
            )
            for n, corr in enumerate(line["corrections"]):
                show_correction(selected, line, n, corr, False, dirty)

with right:
    st.subheader("Note")
    st.caption(f'Version {version} ({note["reason"]}). Edit any statement, and use "Show source" '
               "to see the transcript lines behind it.")
    with pane():
        for key, title in SECTIONS:
            st.markdown(f"**{title}**")
            statements = note["note"][key]
            if not statements:
                st.caption("None recorded.")
            for i, item in enumerate(statements):
                base = f"{selected}_{version}_{key}_{i}"
                st.text_area(f"{title} statement {i + 1}", value=item["text"], key=f"text_{base}",
                             label_visibility="collapsed", height=68)
                a, b = st.columns([1, 1])
                with a:
                    st.button("Show source", key=f"src_{base}",
                              on_click=set_highlight, args=(selected, item["source_lines"], base))
                with b:
                    if item["needs_review"]:
                        st.checkbox("Reviewed", key=f"rev_{base}")
                if item["needs_review"] and not st.session_state.get(f"rev_{base}", False):
                    st.markdown(flag_html(item["review_reason"]), unsafe_allow_html=True)
                if hl and hl["id"] == selected and hl.get("base") == base:
                    for ln in item["source_lines"]:
                        src = lines_by_no.get(ln)
                        if src:
                            st.markdown(
                                line_html(src["line_no"], src["speaker"], src["text"], True,
                                          src.get("low_words", [])),
                                unsafe_allow_html=True,
                            )
                st.caption("Source: lines " + ", ".join(str(n) for n in item["source_lines"]))

show_history()