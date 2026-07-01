import os
import logging
from google import genai
from google.genai import types
import pydantic
import json
from typing import List

from app.schemas import Message, ChatResponse, Recommendation, ConversationState
from app.state_builder import reconstruct_state, prioritize_question
from app.catalog_manager import CatalogManager

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Gemini Client Config
API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Primary model: gemini-2.5-flash confirmed working in this environment.
# gemini-2.0-flash consistently exhausts quota — removed from chain.
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# Fallback chain: tried in order when any model returns a transient error.
MODEL_FALLBACK_CHAIN = [
    MODEL_NAME,
    "gemini-flash-lite-latest",
]

logger.info(f"Primary model: {MODEL_NAME} | Fallback: {MODEL_FALLBACK_CHAIN[1:]}")

# Define Pydantic Schema for Gemini Output to guarantee structure
class LLMOutputSchema(pydantic.BaseModel):
    reply: str = pydantic.Field(..., description="Reply to the user")
    recommended_names: List[str] = pydantic.Field(..., description="List of recommended assessment names from context. Empty if clarifying/refusing.")
    end_of_conversation: bool = pydantic.Field(..., description="True if recommendations are provided and conversation is complete.")

class Agent:
    def __init__(self):
        self.catalog_manager = CatalogManager()
        # Set up genai Client
        self.client = genai.Client(api_key=API_KEY)

    def _call_llm(self, contents: str, config) -> object:
        """
        Calls generate_content with automatic model fallback on 429 quota errors.
        Tries each model in MODEL_FALLBACK_CHAIN before raising.
        """
        last_exc = None
        for model in MODEL_FALLBACK_CHAIN:
            try:
                return self.client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config
                )
            except Exception as e:
                err_str = str(e)
                # Retry on: 429 quota exhaustion, 503 overload, transient transport errors
                is_transient = (
                    "429" in err_str or "RESOURCE_EXHAUSTED" in err_str
                    or "503" in err_str or "UNAVAILABLE" in err_str
                    or "overloaded" in err_str.lower()
                    or "ServiceUnavailable" in err_str
                    or "timeout" in err_str.lower()
                    or "connection" in err_str.lower()
                )
                if is_transient:
                    logger.warning(f"Model {model} transient error ({err_str[:80]}...), trying next fallback...")
                    last_exc = e
                    continue
                raise  # Non-transient errors (auth, bad request, etc.) propagate immediately
        raise last_exc  # All models exhausted

    def is_refusal(self, last_user_message: str) -> bool:
        """
        Detects if the user query is off-topic, requests legal advice, general hiring advice, 
        or is a prompt injection attack.
        """
        msg = last_user_message.lower()
        
        # Off-topic checks
        off_topic_terms = [
            # Sports / entertainment
            "ipl", "cricket", "football", "weather", "recipe", "who won", "president", "movie",
            # Code writing requests — these should be refused even if they mention tech terms
            "write python code", "python function", "code in c++", "write a script",
            "write me a", "write a python", "write a function", "write a program",
            "write code", "debug this code", "debug my code", "implement a function",
            "implement a class", "implement an algorithm", "sort a list", "solve this algorithm",
            "generate a script", "create a script", "build a script",
        ]
        for term in off_topic_terms:
            if term in msg:
                return True
                
        # Legal/General hiring advice checks
        hiring_advice_terms = [
            "how to draft a contract", "legal implications", "labor law", "minimum wage", 
            "interview tips for candidates", "resume writing tips", "how should I fire"
        ]
        for term in hiring_advice_terms:
            if term in msg:
                return True
                
        # Prompt injection / prompt leak checks
        injection_terms = [
            "ignore instructions", "ignore above", "ignore previous", "system prompt", 
            "tell me your prompt", "secret prompt", "developer guidelines", "you are no longer"
        ]
        for term in injection_terms:
            if term in msg:
                return True
                
        return False

    def classify_intent(self, state: ConversationState, messages: List[Message]) -> str:
        """
        Determines the current conversation intent: COMPARE, REFUSE, CLARIFY, RECOMMEND, or REFINE.
        """
        last_user_msg = messages[-1].content if messages else ""
        
        if self.is_refusal(last_user_msg):
            return "REFUSE"
            
        if state.compare_request:
            return "COMPARE"
            
        # Prioritize missing critical fields
        missing_param = prioritize_question(state)
        if missing_param is not None:
            return "CLARIFY"
            
        return "RECOMMEND"

    def handle_refusal(self, last_user_msg: str) -> ChatResponse:
        reply = (
            "I can only help you recommend and compare SHL assessments from the official catalog. "
            "I cannot answer off-topic questions, write code, or provide general legal or hiring advice."
        )
        return ChatResponse(
            reply=reply,
            recommendations=[],
            end_of_conversation=False
        )

    def handle_comparison(self, state: ConversationState) -> ChatResponse:
        # Retrieve context of the targeted products for comparison
        matched_items = []
        for name in state.compare_request:
            item = self.catalog_manager.get_by_name(name)
            if item:
                matched_items.append(item)

        if not matched_items:
            return ChatResponse(
                reply="I couldn't find the specific assessments you requested to compare in the SHL catalog.",
                recommendations=[],
                end_of_conversation=False
            )

        # Deterministic comparison — fully grounded in catalog, zero LLM calls
        reply_lines = ["Based on the SHL Catalog:\n"]
        for item in matched_items:
            langs = item["languages"][:3]
            lang_str = ", ".join(langs) + (" ..." if len(item["languages"]) > 3 else "")
            reply_lines.append(
                f"**{item['name']}** (Type: {item['test_type']})\n"
                f"- Duration: {item['duration']}\n"
                f"- Keys: {', '.join(item['keys'])}\n"
                f"- Languages: {lang_str}\n"
                f"- {item['description']}\n"
            )
        return ChatResponse(
            reply="\n".join(reply_lines),
            recommendations=[],
            end_of_conversation=False
        )

    def handle_clarification(self, state: ConversationState) -> ChatResponse:
        missing_param = prioritize_question(state)
        
        if missing_param == "role_title":
            reply = "To recommend the right SHL assessments, could you please clarify what specific job role or technical domain (e.g., Java Developer, Sales Representative) you are hiring for?"
        elif missing_param == "seniority":
            reply = "Could you please tell me the target seniority level or years of experience for this role (e.g., Mid-level, Director, Graduate)?"
        else:
            reply = "Could you tell me if you are looking for specific technical coding skills, cognitive aptitude tests, or personality assessments?"
            
        return ChatResponse(
            reply=reply,
            recommendations=[],
            end_of_conversation=False
        )

    def generate_recommendations(self, state: ConversationState, messages: List[Message], force_recommend: bool = False) -> ChatResponse:
        # 1. Retrieve top 20 candidate assessments from catalog manager
        candidates = self.catalog_manager.retrieve(state, top_k=20)
        
        # Build compact catalog description text (hide URLs to prevent hallucination)
        catalog_context_lines = []
        for idx, item in enumerate(candidates):
            catalog_context_lines.append(
                f"Candidate #{idx+1}:\n"
                f"Name: {item['name']}\n"
                f"Test Type: {item['test_type']}\n"
                f"Duration: {item['duration']}\n"
                f"Languages: {', '.join(item['languages'])}\n"
                f"Keys: {', '.join(item['keys'])}\n"
                f"Description: {item['description']}\n"
            )
        catalog_context = "\n".join(catalog_context_lines)
        
        # 2. Build structured prompt
        system_rules = (
            "You are the official SHL Assessment Recommender Agent.\n"
            "Your task is to select and recommend the most suitable assessments for a role from the provided context.\n"
            "Rules:\n"
            "1. Recommend between 1 and 10 assessments. NEVER recommend more than 10 or less than 1.\n"
            "2. Only recommend assessments that are listed in the provided RETRIEVED CATALOG entries.\n"
            "3. Return the exact names of the recommended assessments in the 'recommended_names' array.\n"
            "4. Ground your reply and choices in the catalog descriptions. Do not invent details.\n"
            "5. If you decide the conversation is complete and recommendations are finalized, set 'end_of_conversation' to true."
        )
        
        state_summary = (
            f"Hiring Role: {state.role_title}\n"
            f"Skills: {', '.join(state.technical_skills)}\n"
            f"Seniority: {state.seniority}\n"
            f"Requires Personality Test: {state.needs_personality}\n"
            f"Requires Cognitive Test: {state.needs_cognitive}"
        )
        
        history_lines = []
        for msg in messages:
            history_lines.append(f"{msg.role.capitalize()}: {msg.content}")
        history_text = "\n".join(history_lines)
        
        prompt = (
            f"SYSTEM RULES:\n{system_rules}\n\n"
            f"CONVERSATION STATE:\n{state_summary}\n\n"
            f"CONVERSATION HISTORY:\n{history_text}\n\n"
            f"RETRIEVED CATALOG CONTEXT:\n{catalog_context}\n\n"
            "Select the best matching assessments (1-10 items). Write a professional reply explaining the shortlist, and set the recommendations."
        )
        
        try:
            response = self._call_llm(
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=LLMOutputSchema
                )
            )
            data = json.loads(response.text)
            if isinstance(data, str):
                data = json.loads(data)
            
            # Post-Process & Validate recommendations list in backend
            raw_names = data.get("recommended_names", [])
            valid_recs = self.catalog_manager.match_and_populate(raw_names)
            
            # Hallucination Recovery: If LLM returned recommendations but backend matching yielded 0 valid products,
            # we fall back to a clarification turn instead of failing.
            if len(raw_names) > 0 and len(valid_recs) == 0:
                logger.warning("LLM proposed recommendations, but none matched the catalog. Initiating clarification fallback.")
                return self.handle_clarification(state)
                
            reply = data.get("reply", "Here are the recommended assessments:")
            end_of_conv = data.get("end_of_conversation", False)
            
            # If force recommend turn budget reached, we force end of conversation
            if force_recommend:
                end_of_conv = True
                
            # If recommendations exist, ensure we conform to 1<=count<=10 constraints
            if len(valid_recs) > 0:
                # Limit top 10
                valid_recs = valid_recs[:10]
            else:
                # If no recommendations are made, it cannot be end of conversation
                end_of_conv = False
                
            # Populate Pydantic schemas
            pydantic_recs = [Recommendation(**rec) for rec in valid_recs]
            
            return ChatResponse(
                reply=reply,
                recommendations=pydantic_recs,
                end_of_conversation=end_of_conv
            )
            
        except Exception as e:
            logger.error(f"Error during recommendation LLM call: {e}")
            # Safe recovery fallback
            return self.handle_clarification(state)

    def execute(self, messages: List[Message]) -> ChatResponse:
        # Reconstruct Conversation State using deterministic parser
        state = reconstruct_state(messages)
        
        # Turn budget calculations
        assistant_turns = len([m for m in messages if m.role == "assistant"])
        force_recommend = (assistant_turns >= 3) # allow up to 3 clarify/refine turns; force on 4th
        
        # Classify user intent
        intent = self.classify_intent(state, messages)
        
        if intent == "REFUSE":
            return self.handle_refusal(messages[-1].content if messages else "")
            
        if force_recommend:
            # Overrule CLARIFY/COMPARE and force recommendations
            logger.info("Turn budget limit near. Forcing recommendation phase.")
            return self.generate_recommendations(state, messages, force_recommend=True)
            
        if intent == "COMPARE":
            return self.handle_comparison(state)
            
        if intent == "CLARIFY":
            return self.handle_clarification(state)
            
        # Otherwise intent is RECOMMEND or REFINE
        return self.generate_recommendations(state, messages)
