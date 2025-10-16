import json
import ssl
import time
import os
from typing import Optional, List
from pydantic import BaseModel, ValidationError
from dotenv import load_dotenv
from backend.db import insert_log
from backend.prompts import log_analysis_prompt
from langchain_openai.chat_models.azure import AzureChatOpenAI

# Load environment variables
load_dotenv()

# -------------------------
# Pydantic Models
# -------------------------
class Error(BaseModel):
    timestamp: Optional[str] = None
    error_message: str
    error_type: str

class FixSection(BaseModel):
    summary: str
    steps: List[str]

class PossibleSolution(BaseModel):
    error_message: str
    immediate_fix: FixSection
    permanent_fix: FixSection
    preventive_measures: FixSection

class LogAnalysisResponse(BaseModel):
    log_id: Optional[int] = None
    errors: List[Error] = []
    possible_solutions: List[PossibleSolution] = []

# -------------------------
# Azure OpenAI Setup
# -------------------------
API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT")
API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

if not all([API_KEY, AZURE_ENDPOINT, DEPLOYMENT_NAME]):
    raise ValueError("Missing required Azure OpenAI environment variables")

# -------------------------
# Constants
# -------------------------
MAX_LOG_LENGTH = 50000  # Prevent API timeouts
MAX_RETRIES = 3
RETRY_DELAY = 5

# -------------------------
# Analyze Log
# -------------------------
def analyze_log_node(log_text: str) -> dict:
    """Analyze log text using Azure OpenAI and return structured JSON."""
    
    # Truncate if too long
    if len(log_text) > MAX_LOG_LENGTH:
        log_text = log_text[:MAX_LOG_LENGTH] + "\n... [truncated]"
    
    # Initialize LLM
    llm = AzureChatOpenAI(
        azure_endpoint=AZURE_ENDPOINT,
        api_key=API_KEY,
        azure_deployment=DEPLOYMENT_NAME,
        api_version=API_VERSION,
        temperature=0.3,
        max_tokens=4000,
    )

    response = None
    for attempt in range(MAX_RETRIES):
        try:
            formatted_prompt = log_analysis_prompt.format(log_text=log_text)
            response = llm.invoke(formatted_prompt)
            print("=== RAW LLM RESPONSE START ===")
            print(repr(response))
            if hasattr(response, "content"):
                print("=== LLM RESPONSE CONTENT ===")
                print(repr(response.content))
            print("=== RAW LLM RESPONSE END ===")
            break
        except Exception as e:
            print(f"OpenAI request failed ({attempt+1}/{MAX_RETRIES}): {type(e).__name__}('{e}')")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
    
    json_output = {"errors": [], "possible_solutions": []}
    if not response:
        print("No response object received")
        return json_output

    try:
        if hasattr(response, "content"):
            response_text = response.content
            if isinstance(response_text, str):
                response_text = response_text.strip()
                
                # Remove markdown code blocks if present
                if response_text.startswith("```"):
                    lines = response_text.split("\n")
                    # Remove first line if it's ```json or ```
                    if lines[0].strip().startswith("```"):
                        lines = lines[1:]
                    # Remove last line if it's ```
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    response_text = "\n".join(lines).strip()
                
                start_idx = response_text.find('{')
                end_idx = response_text.rfind('}') + 1
                if start_idx != -1 and end_idx > start_idx:
                    json_str = response_text[start_idx:end_idx]
                    print(f"Extracted JSON string: {repr(json_str)}")
                    try:
                        parsed = json.loads(json_str)
                        print(f"Parsed JSON: {parsed}")
                        if isinstance(parsed, dict):
                            json_output = {
                                "errors": parsed.get("errors", []),
                                "possible_solutions": parsed.get("possible_solutions", [])
                            }
                    except json.JSONDecodeError as je:
                        print(f"JSON decode error: {je}")
                        print(f"Failed to parse: {repr(json_str)}")
                else:
                    print("No valid JSON braces found in response")
                    print(f"Full response text: {repr(response_text)}")
            elif isinstance(response_text, dict):
                json_output = {
                    "errors": response_text.get("errors", []),
                    "possible_solutions": response_text.get("possible_solutions", [])
                }
            else:
                print(f"Unexpected response_text type: {type(response_text)}")
        elif isinstance(response, str):
            # Same JSON parsing logic as above for string
            response = response.strip()
            
            # Remove markdown code blocks if present
            if response.startswith("```"):
                lines = response.split("\n")
                if lines[0].strip().startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                response = "\n".join(lines).strip()
            
            start_idx = response.find('{')
            end_idx = response.rfind('}') + 1
            if start_idx != -1 and end_idx > start_idx:
                json_str = response[start_idx:end_idx]
                try:
                    parsed = json.loads(json_str)
                    if isinstance(parsed, dict):
                        json_output = {
                            "errors": parsed.get("errors", []),
                            "possible_solutions": parsed.get("possible_solutions", [])
                        }
                except json.JSONDecodeError as je:
                    print(f"JSON decode error: {je}")
        else:
            print("Response is of unexpected type:", type(response))
    except Exception as e:
        print(f"Error processing response: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

    print(f"Final json_output: {json_output}")
    return json_output


# -------------------------
# Run Analysis
# -------------------------
def run_log_analysis(log_text: str) -> LogAnalysisResponse:
    """Run log analysis using Azure OpenAI, save to DB, and return structured response."""
    if not log_text or not log_text.strip():
        return LogAnalysisResponse()
    
    try:
        result_dict = analyze_log_node(log_text)
        
        # Validate and create response with error handling
        errors = []
        for error_data in result_dict.get("errors", []):
            try:
                errors.append(Error(**error_data))
            except ValidationError as e:
                print(f"Invalid error data: {e}")
                # Try to fix common issues
                if isinstance(error_data, dict):
                    if "timestamp" not in error_data:
                        error_data["timestamp"] = None
                    try:
                        errors.append(Error(**error_data))
                    except ValidationError:
                        pass
        
        solutions = []
        for solution_data in result_dict.get("possible_solutions", []):
            try:
                solutions.append(PossibleSolution(**solution_data))
            except ValidationError as e:
                print(f"Invalid solution data: {e}")
        
        response = LogAnalysisResponse(
            errors=errors,
            possible_solutions=solutions
        )
        
        # Save to DB
        analysis_json = response.model_dump()
        log_id = insert_log(
            error_summary=", ".join([e.error_message for e in response.errors]) or "No errors detected",
            analysis=json.dumps(analysis_json, indent=2)
        )
        response.log_id = log_id
        return response
        
    except Exception as e:
        print(f"Analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return LogAnalysisResponse()

# -------------------------
# Pretty Formatter
# -------------------------
def format_response_readable(response: LogAnalysisResponse) -> str:
    """Format the analysis response in a readable format."""
    lines = [f"📘 Log ID: {response.log_id}\n"]
    
    if response.errors:
        lines.append("🚨 Errors Found:")
        for e in response.errors:
            lines.append(f"- Timestamp: {e.timestamp or 'N/A'}")
            lines.append(f"  Message: {e.error_message}")
            lines.append(f"  Type: {e.error_type}\n")
    else:
        lines.append("✅ No errors detected.\n")
    
    if response.possible_solutions:
        lines.append("\n🧠 Possible Solutions:")
        for ps in response.possible_solutions:
            lines.append(f"\nError: {ps.error_message}")
            for section_name, fix in [
                ("Immediate Fix", ps.immediate_fix),
                ("Permanent Fix", ps.permanent_fix),
                ("Preventive Measures", ps.preventive_measures),
            ]:
                lines.append(f"  🔹 {section_name}: {fix.summary}")
                for step in fix.steps:
                    lines.append(f"    - {step}")
    else:
        lines.append("ℹ️ No possible solutions available.\n")
    
    return "\n".join(lines)