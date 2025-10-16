
import json
import requests
from typing import List, Optional
from pydantic import BaseModel
from langgraph.graph import StateGraph
from backend.prompts import log_analysis_prompt
from backend.db import insert_log
import time
import ssl
import httpx
from langchain_openai.chat_models.azure import AzureChatOpenAI
from dotenv import load_dotenv
import os

load_dotenv()

API_KEY = os.getenv("API_KEY")
# Use the Azure resource base endpoint (no path suffix). The deployment name is passed separately.
AZURE_ENDPOINT = os.getenv("AZURE_ENDPOINT")
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


class PossibleSolution(BaseModel):
    error_message: str
    solutions: List[str]


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
    try:
        response = requests.get(
            f"https://api.duckduckgo.com/?q={error_msg}+site:stackoverflow.com&format=json"
        )
        data = response.json()
        if "RelatedTopics" in data:
            return [t["Text"] for t in data["RelatedTopics"][:3]]
        return []
    except Exception:
        return ["No external solutions found."]



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
    for attempt in range(max_retries):
        try:
            response = llm.invoke(log_analysis_prompt.format(log_text=state.log_text))
            break
        except Exception as e:
            print(f"OpenAI request failed ({attempt+1}/{max_retries}): {e}")
            time.sleep(5)
    else:
        response = '{"errors": [], "possible_solutions": []}'
  
    try:
        json_output = json.loads(response.content)
    except Exception:
        json_output = {"errors": [], "possible_solutions": []}
    return {"structured_output": json_output}


def enrich_with_external_solutions(state: LogAnalysisState) -> dict:
    enriched = state.structured_output
    for sol in enriched.get("possible_solutions", []):
        extra = fetch_stackoverflow_solutions(sol["error_message"])
        sol["solutions"].extend(extra)
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

    # Save to database
    log_id = insert_log(log_text, json.dumps(result["final_output"], indent=2))

    # Convert to model response
    response = LogAnalysisResponse(**result["final_output"])
    response.log_id = log_id  # Attach log ID dynamically
    return response