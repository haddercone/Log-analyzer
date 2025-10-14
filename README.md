# 🧠 LLM Log Analyzer

A full-stack app that:
- Takes frontend logs as input (via Streamlit)
- Sends them to an LLM (via LangChain + LangGraph)
- Parses errors and suggests solutions
- Stores results in SQLite for history view

### 🔧 Setup

```bash
pip install -r requirements.txt
streamlit run main.py
```

### ⚙️ Architecture
- **Frontend:** Streamlit
- **LLM:** LangChain + LangGraph
- **DB:** SQLite (local persistence)
- **Tools:** StackOverflow API (mocked for now)
