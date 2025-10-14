import streamlit as st
import json
from backend.llm_pipeline import run_log_analysis
from backend.db import init_db, insert_log, insert_feedback, fetch_logs

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

                try:
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
                st.markdown("---")
                st.markdown("### **Provide Feedback**")

               # Initialize feedback session state
                if 'feedback_submitted' not in st.session_state:
                    st.session_state.feedback_submitted = False

                st.markdown("---")
                st.markdown("### **Provide Feedback**")

                if not st.session_state.feedback_submitted:
                    # Radio for Yes/No
                    feedback_choice = st.radio(
                        "Was this analysis helpful?", 
                        options=["Yes 👍", "No 👎"],
                        key=f"fb_choice_{log_id}"
                    )
                    # Text area for optional comment
                    feedback_comment = st.text_area(
                        "Add a comment (optional):",
                        key=f"fb_comment_{log_id}",
                        height=80
                    )

                    # Submit button inside the same block
                    if st.button("Submit Feedback", key=f"submit_feedback_{log_id}"):
                        choice = "Yes" if feedback_choice.startswith("Yes") else "No"
                        insert_feedback(log_id, choice, feedback_comment.strip())
                        st.session_state.feedback_submitted = True
                        st.success("✅ Thank you for your feedback!")

                # Display submitted feedback immediately
                if st.session_state.feedback_submitted:
                    row = fetch_logs(log_id)[0]  # fetch this log only
                    fb_choice, fb_text = row[4], row[5]
                    emoji = "👍" if fb_choice.lower().startswith("y") else "👎"
                    st.info(f"**Feedback Recorded:** {emoji} — {fb_text if fb_text else '(no comment)'}")

            except Exception as e:
                st.error(f"An error occurred during analysis: {e}")



# ---------------------------
# Recent Analyses
# ---------------------------
st.markdown("---")
st.header("🕓 Recent Analyses")

try:
    rows = fetch_logs()
    if not rows:
        st.info("No recent analyses found.")
    else:
        for row in rows:
            # row = (id, created_at, error_message, analysis, feedback_choice, feedback_text)
            log_id, created_at, error_message, analysis_text, fb_choice, fb_text = row

            with st.expander(f"Analysis ID {log_id} — {created_at}"):
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
                    fb_display = fb_text if fb_text else "(no comment)"
                    emoji = "👍" if fb_choice.lower().startswith("y") else "👎"
                    st.markdown(f"**Feedback:** {emoji} — {fb_display} (choice: {fb_choice})")
except Exception as e:
    st.error(f"Error fetching recent analyses: {e}")
