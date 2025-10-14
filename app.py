import streamlit as st
import requests
import pandas as pd

API_URL = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="LLM Log Analyzer",
    page_icon="🧠",
    layout="wide"
)

st.title("🧠 LLM Log Analyzer Dashboard")

tabs = st.tabs(["🔍 Analyze Log", "📊 View Results", "💬 Feedback"])

# 🎯 Tab 1 — Analyze
with tabs[0]:
    st.header("Analyze Log File")

    log_input = st.text_area("Paste your log here", height=200)
    if st.button("Analyze Log", type="primary"):
        if log_input.strip():
            with st.spinner("Analyzing log using LLM..."):
                resp = requests.post(f"{API_URL}/analyze-log", json={"log": log_input})
                if resp.status_code == 200:
                    data = resp.json()["errors"]
                    st.success(f"Found {len(data)} error(s) in log.")
                    for err in data:
                        with st.container():
                            st.markdown(
                                f"""<div style='background:{err['color']};padding:10px;border-radius:10px;margin-bottom:10px'>
                                <b>🧩 Error:</b> {err['message']}<br>
                                <b>🧠 Cause:</b> {err['cause']}<br>
                                <b>✅ Solution:</b> {err['solution']}<br>
                                <b>🔗 References:</b> {', '.join(err['references']) if err['references'] else 'None'}<br>
                                <b>🔥 Severity:</b> <b>{err['severity'].upper()}</b>
                                </div>""",
                                unsafe_allow_html=True
                            )
                else:
                    st.error("Error analyzing log.")
        else:
            st.warning("Please paste a log first.")


# 📊 Tab 2 — View Results
with tabs[1]:
    st.header("Stored Analyses")
    if st.button("Refresh Logs"):
        resp = requests.get(f"{API_URL}/logs")
        if resp.status_code == 200:
            logs = resp.json()
            if logs:
                df = pd.DataFrame(logs)
                st.dataframe(df[["message", "cause", "solution", "severity"]])
            else:
                st.info("No logs found in the database.")
        else:
            st.error("Failed to fetch logs.")


# 💬 Tab 3 — Feedback
with tabs[2]:
    st.header("Submit Feedback")
    msg = st.text_area("Error message")
    cause = st.text_area("Corrected cause (optional)")
    sol = st.text_area("Corrected solution")
    sev = st.selectbox("Severity", ["critical", "error", "warning", "info"])

    if st.button("Submit Feedback", type="primary"):
        if msg and sol:
            resp = requests.post(
                f"{API_URL}/feedback",
                json={
                    "error_message": msg,
                    "corrected_cause": cause,
                    "corrected_solution": sol,
                    "severity": sev
                }
            )
            if resp.status_code == 200:
                st.success("✅ Feedback recorded successfully!")
            else:
                st.error("Failed to submit feedback.")
        else:
            st.warning("Please provide an error message and solution.")
