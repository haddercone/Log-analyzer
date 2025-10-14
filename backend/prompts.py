from langchain_core.prompts import PromptTemplate

# Create the PromptTemplate (probably already done in backend/prompts.py)
log_analysis_prompt = PromptTemplate(
    input_variables=["log_text"],
    template="""
You are a log analysis assistant. Analyze the following log text and return JSON like this:
{{
  "errors": [
    {{
      "timestamp": "2025-10-12T00:00:00Z",
      "error_message": "Error details here",
      "error_type": "Type"
    }}
  ],
  "possible_solutions": [
    {{
      "error_message": "Error details here",
      "solutions": ["Step 1", "Step 2"]
    }}
  ]
}}
Log text:
{log_text}
"""
)
