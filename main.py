import streamlit as st
import json
from backend.llm_pipeline import run_log_analysis
from backend.db import (
    init_db,
    insert_log,
    insert_feedback,
    fetch_logs,
    fetch_logs_with_log_id,
    fetch_log_by_id,
)

# Initialize DB (creates tables if missing)
init_db()

st.set_page_config(page_title="Log Analyzer AI", layout="wide")
st.title("🧠 Log Analyzer AI")

# Upload or paste
uploaded_file = st.file_uploader("Upload a log file", type=["txt", "log"])
manual_input = st.text_area("Or paste log content here:", height=200)

log_content = ""
if uploaded_file:
    log_content = uploaded_file.read().decode("utf-8")
elif manual_input and manual_input.strip():
    log_content = manual_input

if st.button("Analyze Logs"):
    if not log_content.strip():
        st.warning("Please upload or paste log content before analyzing.")
    else:
        # Use spinner context
        with st.spinner("Analyzing logs, please wait..."):
            try:
                response = run_log_analysis(log_content)

                # Extract error summary and analysis
                if hasattr(response, "errors"):
                    error_summary = "; ".join(
                        getattr(e, "error_message", str(e)) for e in response.errors
                    )
                else:
                    error_summary = "No errors parsed"

                # Prefer Pydantic v2 model_dump, fall back to dict()/str()
                try:
                    if hasattr(response, "model_dump"):
                        analysis_text = json.dumps(response.model_dump(), indent=2)
                    else:
                        analysis_text = json.dumps(response.dict(), indent=2)
                except Exception:
                    analysis_text = str(response)

                # Insert log once
                log_id = insert_log(error_summary, analysis_text)
                st.session_state.last_log_id = log_id
                st.session_state.last_response = {
                    "error_summary": error_summary,
                    "analysis_text": analysis_text,
                }

                # ✅ Display results after spinner completes
                st.success("✅ Analysis Complete!")
                st.markdown("### **Error Summary**")
                st.write(error_summary)
                st.markdown("### **Detailed Analysis**")
                st.code(analysis_text)

                # ---------------------------
                # Feedback Section
                # ---------------------------
                # Initialize feedback session state for this log
                fb_sub_key = f"feedback_submitted_{log_id}"
                if fb_sub_key not in st.session_state:
                    st.session_state[fb_sub_key] = False

                    st.info("You can provide feedback below after the analysis completes.")

            except Exception as e:
                st.error(f"An error occurred during analysis: {e}")


# Persistent feedback panel: renders whenever a recent analysis was produced and stored
if 'last_log_id' in st.session_state:
    log_id = st.session_state['last_log_id']
    last_response = st.session_state.get('last_response', {})

    st.markdown("---")
    st.markdown("### Provide Feedback for Last Analysis")
    
    if last_response:
        st.markdown("**Error Summary:**")
        st.write(last_response.get('error_summary', ''))

    fb_sub_key = f"feedback_submitted_{log_id}"
    if fb_sub_key not in st.session_state:
        st.session_state[fb_sub_key] = False

    if not st.session_state[fb_sub_key]:
        feedback_choice = st.radio(
            "Was this analysis helpful?",
            options=["Yes 👍", "No 👎"],
            key=f"fb_choice_{log_id}",
        )
        feedback_comment = st.text_area(
            "Add a comment (optional):",
            key=f"fb_comment_{log_id}",
            height=80
        )

        if st.button("Submit Feedback", key=f"submit_feedback_{log_id}"):
            choice = "Yes" if feedback_choice.startswith("Yes") else "No"
            fb_id = insert_feedback(log_id, choice, feedback_comment.strip())
            st.session_state[fb_sub_key] = True
            st.success("✅ Thank you — your feedback was saved.")
            # show persisted feedback
            row = fetch_log_by_id(log_id)
            if row:
                fb_choice_saved, fb_text_saved = row[4], row[5]
                emoji_saved = "👍" if fb_choice_saved and fb_choice_saved.lower().startswith("y") else "👎"
                st.info(f"**Feedback Recorded:** {emoji_saved} — {fb_text_saved if fb_text_saved else ''}")
    else:
        # already submitted for this session/log
        row = fetch_log_by_id(log_id)
        if row:
            fb_choice_saved, fb_text_saved = row[4], row[5]
            emoji_saved = "👍" if fb_choice_saved and fb_choice_saved.lower().startswith("y") else "👎"
            st.info(f"**Feedback Recorded:** {emoji_saved} — {fb_text_saved if fb_text_saved else ''}")



# ---------------------------
# Recent Analyses
# ---------------------------
st.markdown("---")
st.header("🕓 Recent Analyses")

try:
    # Only show logs that include a top-level log_id in their analysis JSON
    rows = fetch_logs_with_log_id()
    rows_reversed = list(reversed(rows))
    # Show only rows whose analysis JSON contains a top-level "log_id" key
    def _analysis_has_log_id(analysis_text: str) -> bool:
        try:
            obj = json.loads(analysis_text)
            return isinstance(obj, dict) and "log_id" in obj
        except Exception:
            return False

    rows = [r for r in rows if _analysis_has_log_id(r[3])]

    if not rows:
        st.info("No recent analyses found.")
    else:
        for idx, row in enumerate(rows_reversed, start=1):
            # row = (id, created_at, error_message, analysis, feedback_choice, feedback_text)
            log_id, created_at, error_message, analysis_text, fb_choice, fb_text = row

            # Show a sequential display index alongside the DB id so it's clear
            # why the first shown analysis might have a DB id > 1 (it was filtered).
            with st.expander(f"Analysis {idx} — {created_at}"):
                st.markdown("**Error Summary:**")
                st.write(error_message)
                st.markdown("**Detailed Analysis:**")
                # try pretty JSON if analysis_text is JSON
                try:
                    st.json(json.loads(analysis_text))
                except Exception:
                    st.code(analysis_text)

                if fb_choice is not None:
                    # Display feedback saved for this log (if any)
                    if fb_text and fb_text.strip():
                        emoji = "👍" if fb_choice.lower().startswith("y") else "👎"
                        st.markdown(f"**Feedback:** {emoji} — {fb_text}")
                    else:
                         emoji = "👍" if fb_choice.lower().startswith("y") else "👎"
                         st.markdown(f"**Feedback:** {emoji}")
                    
except Exception as e:
    st.error(f"Error fetching recent analyses: {e}")
