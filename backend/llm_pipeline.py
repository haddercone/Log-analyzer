import json
import requests
from typing import List, Optional
from pydantic import BaseModel
from langgraph.graph import StateGraph
from backend.prompts_simple import log_analysis_prompt
from backend.db import insert_log
import time
import ssl
import httpx
from langchain_openai.chat_models.azure import AzureChatOpenAI
API_KEY = ""
# Use the Azure resource base endpoint (no path suffix). The deployment name is passed separately.
AZURE_ENDPOINT = ""
DEPLOYMENT_NAME = "gpt-4.1"
cert = "/etc/ssl/cert.pem"
ctx = ssl.create_default_context(cafile=cert)

# ---------------------------
# SCHEMA DEFINITIONS
# ---------------------------


class Error(BaseModel):
    timestamp: str
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
    errors: List[Error]
    possible_solutions: List[PossibleSolution]
    log_id: Optional[int] = None


# ✅ Define LangGraph State Schema
class LogAnalysisState(BaseModel):
    log_text: str
    structured_output: Optional[dict] = None
    final_output: Optional[dict] = None


# ---------------------------
# NODE FUNCTIONS
# ---------------------------

def fetch_stackoverflow_solutions(error_msg: str) -> List[str]:
    """Fetch external solutions for error messages"""
    try:
        # Try DuckDuckGo first
        from urllib.parse import quote_plus
        query = quote_plus(f"{error_msg[:50]} stackoverflow solution")
        response = requests.get(
            f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1",
            timeout=5
        )
        data = response.json()
        
        solutions = []
        if "RelatedTopics" in data and data["RelatedTopics"]:
            for topic in data["RelatedTopics"][:3]:
                if isinstance(topic, dict) and "Text" in topic:
                    solutions.append(topic["Text"][:200] + "...")
        
        if solutions:
            return solutions
        
        # Fallback: Return some generic solutions based on error type
        return get_generic_solutions(error_msg)
        
    except Exception as e:
        print(f"External solution fetch error: {e}")
        return get_generic_solutions(error_msg)

def get_generic_solutions(error_msg: str) -> List[str]:
    """Provide generic solutions based on error patterns"""
    error_lower = error_msg.lower()
    
    if "nullpointerexception" in error_lower:
        return [
            "Add null checks before accessing object methods or properties",
            "Initialize objects properly before use",
            "Use Optional or defensive programming patterns"
        ]
    elif "timeout" in error_lower:
        return [
            "Increase timeout values in configuration",
            "Check network connectivity and latency",
            "Optimize database queries or external API calls"
        ]
    elif "connection" in error_lower:
        return [
            "Check network connectivity and firewall settings",
            "Verify service endpoints and ports are accessible",
            "Implement connection retry logic with exponential backoff"
        ]
    elif "authentication" in error_lower or "authorization" in error_lower:
        return [
            "Verify credentials and API keys are correct",
            "Check token expiration and refresh mechanisms",
            "Review user permissions and access controls"
        ]
    else:
        return [
            "Check application logs for more detailed error information",
            "Review recent code changes that might have caused the issue",
            "Verify system resources (CPU, memory, disk space) are sufficient"
        ]



def analyze_log_node(state: LogAnalysisState) -> dict:
    
    
    llm = AzureChatOpenAI(
        azure_deployment=DEPLOYMENT_NAME,
        api_version="2024-12-01-preview",
        azure_endpoint=AZURE_ENDPOINT,
        api_key=API_KEY,
        http_client=httpx.Client(verify=ctx),
        timeout=60,
        temperature=0,
    )
    
    max_retries = 3
    response = None
    for attempt in range(max_retries):
        try:
            # Format the prompt with the log text
            formatted_prompt = log_analysis_prompt.format(log_text=state.log_text)
            response = llm.invoke(formatted_prompt)
            break
        except Exception as e:
            print(f"OpenAI request failed ({attempt+1}/{max_retries}): {e}")
            time.sleep(5)
    else:
        # If all retries failed, set a default response
        response = None
  
    try:
        if response and hasattr(response, 'content'):
            # Extract JSON from the response content
            response_text = response.content
            
            # Try to extract JSON from the response
            if isinstance(response_text, str):
                # Look for JSON in the response (it might be wrapped in markdown)
                start_idx = response_text.find('{')
                end_idx = response_text.rfind('}') + 1
                if start_idx != -1 and end_idx > start_idx:
                    json_str = response_text[start_idx:end_idx]
                    json_output = json.loads(json_str)
                else:
                    raise ValueError("No JSON found in response")
            else:
                json_output = {"errors": [], "possible_solutions": []}
        else:
            json_output = {"errors": [], "possible_solutions": []}
            
    except Exception as e:
        print(f"JSON parsing error: {e}")
        json_output = {"errors": [], "possible_solutions": []}
        
    return {"structured_output": json_output}


def enrich_with_external_solutions(state: LogAnalysisState) -> dict:
    enriched = state.structured_output or {"errors": [], "possible_solutions": []}
    
    # Only try to enrich if we have solutions
    for sol in enriched.get("possible_solutions", []):
        if "error_message" in sol:
            try:
                # The new format has immediate_fix, permanent_fix, preventive_measures
                # We'll add external solutions to the immediate_fix steps
                extra = fetch_stackoverflow_solutions(sol["error_message"])
                if extra and extra != ["No external solutions found."]:
                    # Add external solutions to immediate_fix steps
                    if "immediate_fix" in sol and "steps" in sol["immediate_fix"]:
                        sol["immediate_fix"]["steps"].extend([
                            "--- External Solutions ---"
                        ] + extra[:2])  # Add top 2 external solutions
            except Exception as e:
                print(f"Error enriching solutions: {e}")
                
    return {"final_output": enriched}


# ---------------------------
# MAIN RUN FUNCTION
# ---------------------------

def run_log_analysis(log_text: str) -> LogAnalysisResponse:
    
    # ✅ Pass schema to StateGraph
    graph = StateGraph(LogAnalysisState)

    graph.add_node("analyze_log", analyze_log_node)
    graph.add_node("enrich", enrich_with_external_solutions)
    graph.add_edge("analyze_log", "enrich")
    graph.set_entry_point("analyze_log")
    graph.set_finish_point("enrich")

    # Compile the graph into an executable app
    app = graph.compile()

    # Run the pipeline
    result = app.invoke({"log_text": log_text})

    # Ensure we have a valid final_output
    final_output = result.get("final_output", {"errors": [], "possible_solutions": []})
    
    # Save to database
    log_id = insert_log(log_text, json.dumps(final_output, indent=2))

    # Convert to model response
    response = LogAnalysisResponse(**final_output)
    response.log_id = log_id  # Attach log ID dynamically
    return response