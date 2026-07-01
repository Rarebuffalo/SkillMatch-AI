from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.schemas import ChatRequest, ChatResponse
from app.agent import Agent

# Setup logging
logger = logging.getLogger(__name__)

app = FastAPI(title="Conversational SHL Assessment Recommender API")

# Add CORS middleware just in case
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instantiate stateless agent
agent = Agent()

@app.get("/health")
def health_check():
    """
    Ready check endpoint. Returns HTTP 200 on success.
    """
    return {"status": "ok"}

@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
    """
    Stateless conversational agent endpoint. Takes entire conversation history 
    and returns the next response.
    """
    if not request.messages:
        raise HTTPException(status_code=400, detail="The messages list cannot be empty.")
        
    try:
        response = agent.execute(request.messages)
        return response
    except Exception as e:
        logger.error(f"Error handling chat request: {e}")
        raise HTTPException(status_code=500, detail="Internal server error executing agent.")
