from langchain_core.prompts import PromptTemplate

# Create the PromptTemplate (probably already done in backend/prompts.py)
log_analysis_prompt = PromptTemplate(
    input_variables=["log_text"],
    template="""
You are a log analysis assistant. Analyze the following log text and return JSON like this along with source link:
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
      "solutions": [
        {{
          "solution_text": "Step 1",
          "search_keywords": "how to fix step 1" 
        }},
        {{
          "solution_text": "Step 2",
          "search_keywords": "how to fix step 2"
        }}
      ]
    }}
  ]
}}
Log text:
{log_text}
"""
)
