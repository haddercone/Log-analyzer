from langchain_core.prompts import PromptTemplate

# Create a simple, working PromptTemplate
log_analysis_prompt = PromptTemplate(
    input_variables=["log_text"],
    template="""You are an expert Root Cause Analysis (RCA) analyst for technical systems.

Your task is to analyze log entries and identify errors and their solutions.

ANALYSIS STEPS:
1. Identify all error events in the log
2. For each error, determine the error type (ApplicationError, SystemError, ConfigError, TimeoutError, etc.)
3. Provide solutions with immediate_fix, permanent_fix, and preventive_measures

REQUIRED OUTPUT FORMAT - Return ONLY valid JSON:
{{
  "errors": [
    {{
      "timestamp": "timestamp or null",
      "error_message": "clear summary of error",
      "error_type": "ApplicationError|SystemError|ConfigError|TimeoutError|etc"
    }}
  ],
  "possible_solutions": [
    {{
      "error_message": "same as matching error_message above",
      "immediate_fix": {{
        "summary": "short overview of immediate fix",
        "steps": [
          "Step 1 with explanation",
          "Step 2 with explanation",
          "Step 3 with explanation"
        ]
      }},
      "permanent_fix": {{
        "summary": "short overview of permanent fix", 
        "steps": [
          "Code/config change with justification",
          "Testing or validation step",
          "Deployment step"
        ]
      }},
      "preventive_measures": {{
        "summary": "short overview of prevention",
        "steps": [
          "Monitoring or alerting setup",
          "Automated validation setup",
          "Process improvement"
        ]
      }}
    }}
  ]
}}

RULES:
- Use only factual evidence from the logs
- If no errors found, return empty arrays for errors and possible_solutions
- Output ONLY the JSON structure above, no additional text

Now analyze this log:

{log_text}

Remember to return ONLY valid JSON in the specified format above.
"""
)