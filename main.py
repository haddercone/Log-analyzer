import streamlit as st
from backend.llm_pipeline import run_log_analysis, format_response_readable
from backend.db import insert_feedback, fetch_logs, init_db
import json
from backend.llm_pipeline import LogAnalysisResponse

st.set_page_config(page_title="Log Analyzer App", layout="wide")

# -------------------------
# Initialize Database
# -------------------------
init_db()

# -------------------------
# Feedback form helper
# -------------------------
def display_feedback_form(log_id: int, key_suffix: str = ""):
    """
    Display a feedback form for a log_id.
    key_suffix ensures unique Streamlit keys.
    """
    # Generate unique keys using log_id and suffix
    form_key = f"feedback_form_{log_id}_{key_suffix}"
    radio_key = f"feedback_radio_{log_id}_{key_suffix}"
    comments_key = f"comments_{log_id}_{key_suffix}"

    with st.form(key=form_key):
        st.write("Was this analysis helpful?")
        feedback = st.radio(
            "Select one:",
            ["Yes", "No"],
            key=radio_key
        )
        comments = st.text_area(
            "Additional comments (optional):",
            key=comments_key
        )

        submitted = st.form_submit_button("Submit Feedback")
        if submitted:
            insert_feedback(log_id, feedback, comments)
            st.success("✅ Thank you for your feedback!")


# -------------------------
# Recent logs display
# -------------------------
def display_recent_logs(limit: int = 10):
    """Display recent log analyses with feedback forms."""
    st.markdown("### 📜 Recent Analyses")
    try:
        recent_logs = fetch_logs(limit=limit)
        if not recent_logs:
            st.info("No recent analyses found.")
            return

        for idx, log in enumerate(recent_logs):
            log_id = log[0]
            timestamp = log[1]
            error_summary = log[2]
            analysis_json = log[3]
            feedback_choice = log[4]
            feedback_text = log[5]

            with st.expander(f"🪵 Log ID: {log_id} | {timestamp}"):
                st.markdown("**Error Summary:**")
                st.code(error_summary, language=None)

                if analysis_json:
                    try:
                        response_dict = json.loads(analysis_json)
                        response_obj = LogAnalysisResponse(**response_dict)
                        st.markdown(f"**Detailed Analysis (Log ID: {response_obj.log_id})**")
                        readable_text = format_response_readable(response_obj)
                        st.text_area(
                            "Formatted Output", 
                            readable_text, 
                            height=400,
                            key=f"text_area_{log_id}_{idx}"
                        )
                    except Exception as e:
                        st.error(f"Error parsing response JSON: {e}")
                        st.code(analysis_json, language="json")
                
                if feedback_choice:
                    st.markdown(f"**Previous Feedback:** {feedback_choice}")
                    if feedback_text:
                        st.markdown(f"**Comments:** {feedback_text}")
                else:
                    # Only show feedback form if no feedback exists
                    display_feedback_form(log_id, f"recent_{idx}")

    except Exception as e:
        st.error(f"Error fetching recent analyses: {e}")
        import traceback
        st.code(traceback.format_exc())


# -------------------------
# Main Streamlit App
# -------------------------
def main():
    st.title("🔍 Log Analyzer App")
    st.markdown("Analyze system logs and get intelligent root cause analysis with actionable solutions.")

    # Initialize session_state variables
    if "log_text" not in st.session_state:
        st.session_state.log_text = ""
    if "analysis_response" not in st.session_state:
        st.session_state.analysis_response = None

    # Create tabs for better UX
    tab1, tab2 = st.tabs(["📝 Analyze New Log", "📜 History"])
    
    with tab1:
        # Text area (bind to session_state)
        log_text = st.text_area(
            "Paste your log text here:",
            value=st.session_state.log_text,
            height=300,
            placeholder="Paste application, system, CI/CD, or cloud infrastructure logs..."
        )
        st.session_state.log_text = log_text

        # Analyze button
        col1, col2 = st.columns([1, 5])
        with col1:
            analyze_button = st.button("🔍 Analyze Log", type="primary")
        with col2:
            if st.button("🗑️ Clear"):
                st.session_state.log_text = ""
                st.session_state.analysis_response = None
                st.rerun()

        if analyze_button:
            if not st.session_state.log_text.strip():
                st.warning("⚠️ Please paste some log text before analyzing.")
            else:
                with st.spinner("🔄 Analyzing logs..."):
                    st.session_state.analysis_response = run_log_analysis(st.session_state.log_text)

        # Display analysis result if exists
        if st.session_state.analysis_response:
            response = st.session_state.analysis_response

            st.success("✅ Analysis Complete!")
            st.divider()
            
            # Display errors
            if response.errors:
                st.markdown("### 🚨 Errors Detected")
                for i, error in enumerate(response.errors, 1):
                    with st.expander(f"Error {i}: {error.error_type}", expanded=(i == 1)):
                        col1, col2 = st.columns([1, 3])
                        with col1:
                            st.write("**Timestamp:**")
                            st.write("**Type:**")
                        with col2:
                            st.write(error.timestamp or "N/A")
                            st.write(error.error_type)
                        st.write("**Message:**")
                        st.info(error.error_message)
            else:
                st.info("ℹ️ No errors detected in the logs.")
            
            # Display solutions
            if response.possible_solutions:
                st.divider()
                st.markdown("### 💡 Possible Solutions")
                for i, solution in enumerate(response.possible_solutions, 1):
                    with st.expander(f"Solution {i} for: {solution.error_message}", expanded=(i == 1)):
                        # Immediate Fix
                        st.markdown("#### 🚑 Immediate Fix")
                        st.write(solution.immediate_fix.summary)
                        for step in solution.immediate_fix.steps:
                            st.markdown(f"- {step}")
                        
                        st.divider()
                        
                        # Permanent Fix
                        st.markdown("#### 🔧 Permanent Fix")
                        st.write(solution.permanent_fix.summary)
                        for step in solution.permanent_fix.steps:
                            st.markdown(f"- {step}")
                        
                        st.divider()
                        
                        # Preventive Measures
                        st.markdown("#### 🛡️ Preventive Measures")
                        st.write(solution.preventive_measures.summary)
                        for step in solution.preventive_measures.steps:
                            st.markdown(f"- {step}")

            # Feedback form for the analyzed log
            if response.log_id:
                st.divider()
                st.markdown("### 📝 Feedback")
                display_feedback_form(response.log_id, "current")

    with tab2:
        # Show recent logs in the history tab
        display_recent_logs()


if __name__ == "__main__":
    main()