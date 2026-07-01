# SkillMatch AI — Conversational SHL Assessment Recommender

An intelligent conversational agent built with FastAPI and Gemini that acts as a solutions engineer, helping recruiters select the best SHL talent assessment products for their hiring needs. The agent dynamically collects requirements (seniority, role domain, test type preferences) and generates a matched, catalog-grounded shortlist.

---

## Features
* **FastAPI API**: High-performance, asynchronous REST API.
* **Stateless Conversation**: Reconstructs state deterministically from chat history on each turn.
* **Hybrid Retrieval**: Employs combination of BM25 text retrieval and semantic scoring.
* **Gemini-Powered Reasoning**: Leverages structured JSON generation and fallback chains.
* **Catalog-Grounded Recommendations**: Guarantees all shortlists match active catalog items.
* **Robust Guardrails**: Rejects off-topic, code generation, and prompt injection queries.

---

## Tech Stack
* **Language**: Python 3.12+
* **Framework**: FastAPI
* **LLM Client**: Google GenAI SDK (google-genai)
* **LLM Engine**: Gemini 2.5 Flash / Gemini Flash Lite (Fallback)
* **Dependencies**: Pydantic, Uvicorn

---

## Installation & Setup

### 1. Clone & Initialize
```bash
git clone https://github.com/Rarebuffalo/SkillMatch-AI.git
cd SkillMatch-AI
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables
```bash
export GEMINI_API_KEY="your-gemini-api-key"
```

---

## Running the Application

### Start the Server
```bash
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Run the Evaluation Harness
To execute the replay traces and verify Recall@10:
```bash
python3 scripts/run_eval.py
```

---

## API Endpoints

### 1. Health Check
`GET /health`

**Example Response**:
```json
{
  "status": "ok"
}
```

### 2. Chat / Recommendation
`POST /chat`

**Example Request**:
```json
{
  "messages": [
    {
      "role": "user",
      "content": "I need assessments for a senior Java developer."
    }
  ]
}
```

**Example Response**:
```json
{
  "reply": "Based on the requirements for a Senior Java Developer, I recommend the following assessments to evaluate Java programming skills, enterprise frameworks, and general logical reasoning abilities:",
  "recommendations": [
    {
      "name": "Core Java (Advanced Level) (New)",
      "url": "https://www.shl.com/products/product-catalog/view/core-java-advanced-level-new/",
      "test_type": "K"
    },
    {
      "name": "Java Frameworks (New)",
      "url": "https://www.shl.com/products/product-catalog/view/java-frameworks-new/",
      "test_type": "K"
    },
    {
      "name": "Verify - Inductive Reasoning (2014)",
      "url": "https://www.shl.com/products/product-catalog/view/verify-inductive-reasoning-2014/",
      "test_type": "A"
    }
  ],
  "end_of_conversation": true
}
```

---

## Project Structure

```
├── app/
│   ├── main.py             # FastAPI entrypoint & router definitions
│   ├── agent.py            # Main conversation orchestration & LLM interaction
│   ├── state_builder.py    # Deterministic parser for reconstructing conversation state
│   ├── catalog_manager.py  # Catalog loader, search, indexing, & matching logic
│   └── schemas.py          # Pydantic schemas for request/response payloads
├── scripts/
│   └── run_eval.py         # Evaluation replay harness & guardrail test runner
├── architecture/           # Deep-dive architecture and design decisions docs
│   ├── design_decisions.md
│   ├── core_logic.md
│   └── evaluation_and_lessons.md
├── requirements.txt        # Python package dependencies
├── .gitignore              # Files to ignore in git repository
└── README.md               # Project documentation
```

---

## Architecture Documentation
* **[Design Decisions](architecture/design_decisions.md)**: State design patterns, safety guardrails, and Gemini integration.
* **[Core Logic & Working](architecture/core_logic.md)**: Deterministic parser, BM25 scoring, and turn-budget overrides.
* **[Evaluation & Lessons Learned](architecture/evaluation_and_lessons.md)**: Recall@10 optimization steps and fallback behavior analysis.
