import json
import requests
import os
from typing import List, Optional
from urllib.parse import quote_plus
from pydantic import BaseModel
#from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph
from backend.prompts import log_analysis_prompt
from backend.db import insert_log
import time
#import openai
import ssl
import httpx
from langchain_openai.chat_models.azure import AzureChatOpenAI

import certifi
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
os.environ.setdefault("SSL_CERT_FILE", certifi.where())

# ---------------------------
# SCHEMA DEFINITIONS
# ---------------------------
API_KEY = ""
# Use the Azure resource base endpoint (no path suffix). The deployment name is passed separately.
AZURE_ENDPOINT = ""
DEPLOYMENT_NAME = "gpt-4.1"
cert = "/etc/ssl/cert.pem"
ctx = ssl.create_default_context(cafile=cert)

class Error(BaseModel):
    timestamp: str
    error_message: str
    error_type: str

class Solution(BaseModel):
    solution_text: str
    source_links: List[str] = []


class PossibleSolution(BaseModel):
    error_message: str
    solutions: List[Solution]


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

def fetch_stackoverflow_solutions(error_msg: str) -> List[dict]:
    """Return a small list of StackOverflow-style results from DuckDuckGo Instant Answer API.

    Each item is a dict: {"title": ..., "url": ...}
    """
    try:
        q = requests.utils.requote_uri(f"{error_msg} site:stackoverflow.com")
        response = requests.get(f"https://api.duckduckgo.com/?q={q}&format=json", verify=certifi.where())
        data = response.json()
        results: List[dict] = []
        related = data.get("RelatedTopics") or []
        for t in related:
            # Some entries have nested "Topics"
            if isinstance(t, dict) and "Topics" in t and isinstance(t["Topics"], list):
                for sub in t["Topics"]:
                    title = sub.get("Text")
                    url = sub.get("FirstURL")
                    if title and url:
                        results.append({"title": title, "url": url})
            else:
                title = t.get("Text") if isinstance(t, dict) else None
                url = t.get("FirstURL") if isinstance(t, dict) else None
                if title and url:
                    results.append({"title": title, "url": url})
        return results[:3]
    except Exception:
        return []


def search_stackoverflow(query: str, max_results: int = 3) -> List[str]:
    """Use the Stack Exchange API to search StackOverflow and return question links."""
    try:
        params = {
            "order": "desc",
            "sort": "relevance",
            "site": "stackoverflow",
            "intitle": query,
            "pagesize": max_results,
        }
        resp = requests.get("https://api.stackexchange.com/2.3/search", params=params, timeout=10, verify=certifi.where())
        data = resp.json()
        links: List[str] = []
        for item in data.get("items", [])[:max_results]:
            link = item.get("link")
            if link:
                links.append(link)
        return links
    except Exception:
        return []



def analyze_log_node(state: LogAnalysisState) -> dict:
    

    # llm = ChatOpenAI(
    #     model="gpt-4o-mini",
    #     temperature=0,
    #     api_key="",
    #     request_timeout=60
    # )

    # Use the LangChain Azure chat model wrapper which calls the chat/completions API.
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
    prompt_text = log_analysis_prompt.format(log_text=state.log_text)

    # Build chat messages: user message contains the prompt
    messages = [
        ("user", prompt_text),
    ]

    for attempt in range(max_retries):
        try:
            ai_msg = llm.invoke(messages)
            # ai_msg can be an object with `.content` or a string
            if isinstance(ai_msg, str):
                response_text = ai_msg
            else:
                # Prefer `.content`; if it's a list or other, coerce to string
                content = getattr(ai_msg, "content", None)
                if isinstance(content, list):
                    # Join parts if returned as list
                    response_text = "".join(map(str, content))
                else:
                    response_text = str(content) if content is not None else str(ai_msg)
            break
        except Exception as e:
            print(f"OpenAI request failed ({attempt+1}/{max_retries}): {e}")
            time.sleep(5)
    else:
        response_text = '{"errors": [], "possible_solutions": []}'

    try:
        json_output = json.loads(response_text)
    except Exception:
        # If the model returned non-JSON, fall back to empty arrays
        json_output = {"errors": [], "possible_solutions": []}
    return {"structured_output": json_output}


def enrich_with_external_solutions(state: LogAnalysisState) -> dict:
    enriched = state.structured_output
    for sol in enriched.get("possible_solutions", []):
        # Ensure solutions exists
        existing = sol.get("solutions") or []

        # If the model provided a search_keywords for each solution, use that to fetch links;
        # otherwise fall back to searching by the error message.
        external_urls = []
        for s in (sol.get("solutions") or []):
            # If s is a dict and has 'search_keywords', use that
            if isinstance(s, dict) and s.get("search_keywords"):
                kws = s.get("search_keywords")
                links = search_stackoverflow(kws)
                # attach links to this specific solution
                s_links = links
            else:
                # fallback: search by the error_message
                links = search_stackoverflow(sol.get("error_message", ""))
                s_links = links

            # ensure we have solution text
            if isinstance(s, dict):
                text = s.get("solution_text") or s.get("text") or str(s)
            else:
                text = str(s)

            # If no links found from the API, provide a StackOverflow search URL as fallback
            if not s_links:
                query_for_search = None
                if isinstance(s, dict) and s.get("search_keywords"):
                    query_for_search = s.get("search_keywords")
                else:
                    query_for_search = sol.get("error_message", "")

                fallback = f"https://stackoverflow.com/search?q={quote_plus(query_for_search)}"
                s_links = [fallback]

            new_solution = {"solution_text": text, "source_links": s_links}
            external_urls.append(new_solution)

        # Replace sol["solutions"] with enriched structured solutions
        sol["solutions"] = external_urls
        
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