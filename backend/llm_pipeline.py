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
# Helper Functions
# -------------------------
def extract_json_from_text(text: str) -> dict:
    """
    Extract and parse JSON from text that may contain markdown or other formatting.
    Returns empty dict with errors/possible_solutions keys if parsing fails.
    """
    if not text:
        return {"errors": [], "possible_solutions": []}
    
    try:
        # Remove leading/trailing whitespace
        text = text.strip()
        
        # Remove markdown code blocks
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line if it starts with ```
            if lines and lines[0].strip().startswith("```"):
                lines = lines[1:]
            # Remove last line if it's just ```
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        
        # Find JSON boundaries
        start_idx = text.find('{')
        end_idx = text.rfind('}') + 1
        
        if start_idx == -1 or end_idx <= start_idx:
            print(f"No JSON braces found in text: {text[:200]}")
            return {"errors": [], "possible_solutions": []}
        
        json_str = text[start_idx:end_idx]
        print(f"Extracted JSON string (first 500 chars): {json_str[:500]}")
        
        # Parse JSON
        parsed = json.loads(json_str)
        
        if not isinstance(parsed, dict):
            print(f"Parsed result is not a dict: {type(parsed)}")
            return {"errors": [], "possible_solutions": []}
        
        # Ensure required keys exist
        result = {
            "errors": parsed.get("errors", []),
            "possible_solutions": parsed.get("possible_solutions", [])
        }
        
        print(f"Successfully parsed JSON with {len(result['errors'])} errors and {len(result['possible_solutions'])} solutions")
        return result
        
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
        print(f"Failed JSON string (first 500 chars): {json_str[:500] if 'json_str' in locals() else 'N/A'}")
        return {"errors": [], "possible_solutions": []}
    except Exception as e:
        print(f"Unexpected error in extract_json_from_text: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return {"errors": [], "possible_solutions": []}


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
    last_error = None
    
    for attempt in range(MAX_RETRIES):
        try:
            formatted_prompt = log_analysis_prompt.format(log_text=log_text)
            response = llm.invoke(formatted_prompt)
            
            print(f"\n=== LLM RESPONSE ATTEMPT {attempt + 1} ===")
            print(f"Response type: {type(response)}")
            print(f"Response repr: {repr(response)[:500]}")
            
            if hasattr(response, "content"):
                print(f"Response.content type: {type(response.content)}")
                print(f"Response.content (first 500 chars): {repr(response.content)[:500]}")
            
            # If we got a response, break and process it
            break
            
        except Exception as e:
            last_error = e
            print(f"\nOpenAI request failed ({attempt+1}/{MAX_RETRIES}): {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            
            if attempt < MAX_RETRIES - 1:
                print(f"Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
    
    # Process response
    json_output = {"errors": [], "possible_solutions": []}
    
    if not response:
        print(f"\nNo response received after {MAX_RETRIES} attempts")
        if last_error:
            print(f"Last error: {last_error}")
        return json_output

    try:
        # Extract content from response
        response_text = None
        
        if hasattr(response, "content"):
            response_text = response.content
        elif isinstance(response, str):
            response_text = response
        elif isinstance(response, dict):
            # Response is already a dict
            json_output = {
                "errors": response.get("errors", []),
                "possible_solutions": response.get("possible_solutions", [])
            }
            print("Response is already a dictionary")
            return json_output
        else:
            print(f"Unexpected response type: {type(response)}")
            return json_output
        
        # Parse text response
        if isinstance(response_text, str):
            json_output = extract_json_from_text(response_text)
        elif isinstance(response_text, dict):
            json_output = {
                "errors": response_text.get("errors", []),
                "possible_solutions": response_text.get("possible_solutions", [])
            }
        else:
            print(f"Unexpected response_text type: {type(response_text)}")
            
    except Exception as e:
        print(f"\nError processing response: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

    print(f"\nFinal json_output: {len(json_output.get('errors', []))} errors, {len(json_output.get('possible_solutions', []))} solutions")
    return json_output


# -------------------------
# Run Analysis
# -------------------------
def run_log_analysis(log_text: str) -> LogAnalysisResponse:
    """Run log analysis using Azure OpenAI, save to DB, and return structured response."""
    if not log_text or not log_text.strip():
        print("Empty log text provided")
        return LogAnalysisResponse()
    
    try:
        print(f"\nStarting log analysis for text of length {len(log_text)}")
        result_dict = analyze_log_node(log_text)
        
        print(f"\nValidating results...")
        
        # Validate and create response with error handling
        errors = []
        for i, error_data in enumerate(result_dict.get("errors", [])):
            try:
                if not isinstance(error_data, dict):
                    print(f"Error {i} is not a dict: {type(error_data)}")
                    continue
                    
                errors.append(Error(**error_data))
                print(f"Validated error {i}: {error_data.get('error_type', 'Unknown')}")
                
            except ValidationError as e:
                print(f"Invalid error data at index {i}: {e}")
                # Try to fix common issues
                if isinstance(error_data, dict):
                    if "timestamp" not in error_data:
                        error_data["timestamp"] = None
                    if "error_message" not in error_data:
                        error_data["error_message"] = "Unknown error"
                    if "error_type" not in error_data:
                        error_data["error_type"] = "UnknownError"
                    try:
                        errors.append(Error(**error_data))
                        print(f"Fixed and validated error {i}")
                    except ValidationError as e2:
                        print(f"Could not fix error {i}: {e2}")
        
        solutions = []
        for i, solution_data in enumerate(result_dict.get("possible_solutions", [])):
            try:
                if not isinstance(solution_data, dict):
                    print(f"Solution {i} is not a dict: {type(solution_data)}")
                    continue
                    
                solutions.append(PossibleSolution(**solution_data))
                print(f"Validated solution {i}")
                
            except ValidationError as e:
                print(f"Invalid solution data at index {i}: {e}")
                print(f"Solution data: {solution_data}")
        
        response = LogAnalysisResponse(
            errors=errors,
            possible_solutions=solutions
        )
        
        print(f"\nCreated response with {len(errors)} errors and {len(solutions)} solutions")
        
        # Save to DB
        analysis_json = response.model_dump()
        log_id = insert_log(
            error_summary=", ".join([e.error_message for e in response.errors]) or "No errors detected",
            analysis=json.dumps(analysis_json, indent=2)
        )
        response.log_id = log_id
        
        print(f"Saved to database with log_id: {log_id}")
        return response
        
    except Exception as e:
        print(f"\nAnalysis failed with exception: {type(e).__name__}: {e}")
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