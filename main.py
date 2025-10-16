import streamlit as st
import json
from backend.llm_pipeline import run_log_analysis
from backend.db import (
    init_db,
    insert_log,
    insert_feedback,
    fetch_logs_with_log_id,
    fetch_log_by_id,
)
import time


# Helper: robustly request a Streamlit rerun. Some Streamlit versions don't have
# st.experimental_rerun(), so fall back to setting a query param (which triggers
# a rerun) or st.stop() as a last resort.
def _maybe_rerun():
    try:
        rerun = getattr(st, "experimental_rerun", None)
        if callable(rerun):
            rerun()
            return
        try:
            st.query_params = {"_refresh": int(time.time())}
            return
        except Exception:
            pass
        try:
            st.stop()
        except Exception:
            return
    except Exception:
        return


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


# ANALYZE BUTTON
if st.button("Analyze Logs"):
    if not log_content.strip():
        st.warning("Please upload or paste log content before analyzing.")
    else:
        with st.spinner("Analyzing logs, please wait..."):
            try:
                response = run_log_analysis(log_content)

                # Extract error summary
                if hasattr(response, "errors"):
                    error_summary = "; ".join(
                        getattr(e, "error_message", str(e)) for e in response.errors
                    )
                else:
                    error_summary = "No errors parsed"

                # analysis as JSON text when possible
                try:
                    analysis_text = json.dumps(response.model_dump(), indent=2)
                except Exception:
                    analysis_text = str(response)

                # Insert log once and save last_log_id in session
                log_id = insert_log(error_summary, analysis_text)
                st.session_state['last_log_id'] = log_id
                st.session_state['last_response'] = {
                    "error_summary": error_summary,
                    "analysis_text": analysis_text,
                }

                st.success("✅ Analysis Complete!")

            except Exception as e:
                st.error(f"An error occurred during analysis: {e}")


# If we have a last analysis stored in session state, render its details
if 'last_response' in st.session_state:
    last = st.session_state['last_response']
    st.markdown("---")
    st.markdown("### **Last Analysis Details**")
    st.markdown("**Error Summary:**")
    st.write(last.get('error_summary', ''))

    analysis_text = last.get('analysis_text', '')
    # try to parse and render structured content (errors, possible_solutions)
    try:
        obj = json.loads(analysis_text)
    except Exception:
        obj = None

    if isinstance(obj, dict):
        # Errors
        if 'errors' in obj and obj['errors']:
            st.markdown("### **🚨 Errors Detected**")
            for i, error in enumerate(obj['errors'], 1):
                with st.expander(f"Error {i}: {error.get('error_type', '')}"):
                    if 'timestamp' in error:
                        st.write(f"**Timestamp:** {error.get('timestamp')}")
                    st.write(f"**Message:** {error.get('error_message', '')}")
                    st.write(f"**Type:** {error.get('error_type', '')}")

        # Possible solutions
        if 'possible_solutions' in obj and obj['possible_solutions']:
            st.markdown("### **💡 Detailed Solutions**")
            for i, sol in enumerate(obj['possible_solutions'], 1):
                title = sol.get('error_message') or f"Solution {i}"
                with st.expander(f"Solution {i}: {str(title)[:60]}..."):
                    # Immediate Fix
                    im = sol.get('immediate_fix', {})
                    if im:
                        st.markdown("#### 🔧 **Immediate Fix**")
                        st.write(f"**Summary:** {im.get('summary', '')}")
                        if im.get('steps'):
                            st.markdown("**Steps:**")
                            for step in im.get('steps'):
                                st.write(f"• {step}")

                    # Permanent Fix
                    pf = sol.get('permanent_fix', {})
                    if pf:
                        st.markdown("#### 🔨 **Permanent Fix**")
                        st.write(f"**Summary:** {pf.get('summary', '')}")
                        if pf.get('steps'):
                            st.markdown("**Steps:**")
                            for step in pf.get('steps'):
                                st.write(f"• {step}")

                    # Preventive Measures
                    pm = sol.get('preventive_measures', {})
                    if pm:
                        st.markdown("#### 🛡️ **Preventive Measures**")
                        st.write(f"**Summary:** {pm.get('summary', '')}")
                        if pm.get('steps'):
                            st.markdown("**Steps:**")
                            for step in pm.get('steps'):
                                st.write(f"• {step}")
    else:
        # fallback: show raw JSON/text
        with st.expander("📋 Raw JSON Output"):
            st.code(analysis_text)



# ---------------------------
# Persistent Feedback Panel (survives reruns)
# ---------------------------
if 'last_log_id' in st.session_state:
    last_log_id = st.session_state['last_log_id']

    fb_sub_key = f"feedback_submitted_{last_log_id}"
    if fb_sub_key not in st.session_state:
        # default: user hasn't submitted feedback for this log in this session
        st.session_state[fb_sub_key] = False

    # Show the header/form only if the current session hasn't submitted
    if not st.session_state[fb_sub_key]:
        st.markdown("---")
        st.markdown("### **Provide Feedback for Last Analysis**")

        with st.form(key=f"fb_form_{last_log_id}"):
            feedback_choice = st.radio(
                "Was the last analysis helpful?",
                options=["Yes 👍", "No 👎"],
                key=f"fb_choice_{last_log_id}"
            )
            feedback_comment = st.text_area(
                "Add a comment (optional):",
                key=f"fb_comment_{last_log_id}",
                height=80
            )
            submitted = st.form_submit_button("Submit Feedback")
            if submitted:
                choice = "Yes" if feedback_choice.startswith("Yes") else "No"
                insert_feedback(last_log_id, choice, feedback_comment.strip())
                st.session_state[fb_sub_key] = True
                # Show a compact success message (header/form will be hidden now)
                st.success("✅ Feedback recorded for the last analysis.")
                _maybe_rerun()
    else:
        # After submit, hide header/form styling and show a compact confirmation
        st.success("✅ Feedback recorded.")

        # Also show the saved feedback (compact)
        row = fetch_log_by_id(last_log_id)
        if row:
            _, _, _, _, fb_choice, fb_text = row
            if fb_choice:
                emoji = "👍" if fb_choice.lower().startswith("y") else "👎"
                st.info(f"{emoji} — {fb_text if fb_text else '(no comment)'}")


# ---------------------------
# Recent Analyses (only canonical rows with a top-level log_id)
# ---------------------------
st.markdown("---")
st.header("🕓 Recent Analyses")

try:
    rows = fetch_logs_with_log_id()
    if not rows:
        st.info("No recent analyses found.")
    else:
        for row in rows:
            log_id, created_at, error_message, analysis_text, fb_choice, fb_text = row

            with st.expander(f"Analysis ID {log_id} — {created_at}"):
                st.markdown("**Error Summary:**")
                st.write(error_message)
                st.markdown("**Detailed Analysis:**")
                try:
                    st.json(json.loads(analysis_text))
                except Exception:
                    st.code(analysis_text)

                if fb_choice is not None:
                    fb_display = fb_text if fb_text else "(no comment)"
                    emoji = "👍" if fb_choice.lower().startswith("y") else "👎"
                    st.markdown(f"**Feedback:** {emoji} — {fb_display} (choice: {fb_choice})")
except Exception as e:
    st.error(f"Error fetching recent analyses: {e}")
    
