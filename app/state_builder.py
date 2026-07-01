import re
import os
import json
from pathlib import Path
from app.schemas import ConversationState

# Resolve catalog path relative to project root at data/shl_product_catalog.json
BASE_DIR = Path(__file__).resolve().parent.parent
CATALOG_PATH = str(BASE_DIR / "data" / "shl_product_catalog.json")
if not os.path.exists(CATALOG_PATH):
    # Search root folder fallback
    CATALOG_PATH = "shl_product_catalog.json"
    if not os.path.exists(CATALOG_PATH):
        CATALOG_PATH = "/home/Krishna-Singh/Downloads/shl_product_catalog.json"


_catalog_names = []

def _get_catalog_names():
    global _catalog_names
    if not _catalog_names:
        if os.path.exists(CATALOG_PATH):
            try:
                with open(CATALOG_PATH, "r", encoding="utf-8") as f:
                    raw = json.load(f, strict=False)
                    _catalog_names = [item.get("name", "") for item in raw if item.get("name")]
            except Exception:
                pass
    return _catalog_names

# Keywords for extraction
SENIORITY_KEYWORDS = {
    "cxo": "Executive",
    "executive": "Executive",
    "director": "Director",
    "vice president": "Director",
    "vp": "Director",
    "senior manager": "Manager",
    "manager": "Manager",
    "supervisor": "Supervisor",
    "senior": "Senior",
    "lead": "Senior",
    "mid-level": "Mid-Professional",
    "mid level": "Mid-Professional",
    "mid": "Mid-Professional",
    "junior": "Entry-Level",
    "entry": "Entry-Level",
    "graduate": "Graduate",
    "intern": "Entry-Level",
    "student": "Entry-Level"
}

TECH_KEYWORDS = [
    "java", "rust", "python", "c\\+\\+", "c\\#", "dotnet", "\\.net", "javascript", "sql", "linux", 
    "networking", "network", "cloud", "aws", "azure", "docker", "kubernetes", "html", "css", 
    "react", "angular", "vue", "php", "ruby", "security", "cybersecurity", "git", "excel",
    "word", "powerpoint", "office", "sap", "oracle"
]

PERSONALITY_KEYWORDS = [
    "personality", "behavior", "behaviour", "soft skill", "soft-skill", "work style", "opq", 
    "competency", "leadership", "character", "interpersonal", "motivation", "sales style"
]

COGNITIVE_KEYWORDS = [
    "cognitive", "aptitude", "ability", "reasoning", "gsa", "verify", "numerical", "inductive", 
    "deductive", "critical thinking", "critical", "math", "verbal", "spatial", "intelligence",
    "problem solving", "problem-solving"
]

def reconstruct_state(messages) -> ConversationState:
    """
    Parses the conversation messages sequentially to reconstruct the user's requirements.
    """
    state = ConversationState()
    
    # Track accumulated context from user turns
    user_inputs = [msg.content.lower() for msg in messages if msg.role == "user"]
    
    if not user_inputs:
        return state
        
    full_text = " ".join(user_inputs)
    
    # 1. Target Role Title extraction
    # Look for patterns: "hiring a ...", "need a ...", "looking for a ...", "developer who works with ..."
    role_match = re.search(r'\bhiring\s+(?:a\s+|an\s+)?([^.\,!?—;:(]+?)(?:\s+(?:in|at|for|with|to|as)\b|\.|\,|\?|\!|—|$)', full_text)
    if role_match:
        state.role_title = role_match.group(1).strip()
    else:
        # Fallback to "need a ..."
        need_match = re.search(r'\bneed\s+(?:a\s+|an\s+)?(?:solution\s+for\s+)?(?:to\s+)?([^.\,!?—;:(]+?)(?:\s+(?:in|at|for|with|to|as)\b|\.|\,|\?|\!|—|$)', full_text)
        if need_match:
            state.role_title = need_match.group(1).strip()
            
    # Clean up role title to represent actual hiring target
    if state.role_title:
        role_title = state.role_title.lower()
        while True:
            prev = role_title
            role_title = re.sub(
                r'^(?:to|be|re-skill|reskill|re-skilling|reskilling|assess|assessing|test|testing|evaluate|evaluating|train|training|hiring|hire|recruit|recruiting|select|selecting|audit|auditing|our|a|an|the|for|solution|solutions|of|in|at|with|as)\s+',
                '',
                role_title
            )
            role_title = role_title.strip()
            if role_title == prev:
                break
                
        # Remove language preferences
        role_title = re.sub(r'\b(?:spanish|english|french|german|bilingual|portuguese|italian|chinese|japanese|korean|vietnamese)\b', '', role_title)
        role_title = re.sub(r'\s+', ' ', role_title).strip()
        role_title = role_title.strip(".,-— ")
        state.role_title = role_title

    if len(state.role_title) > 50:
        state.role_title = state.role_title[:50]

    # 2. Technical Skills extraction
    for tech in TECH_KEYWORDS:
        if re.search(r'\b' + tech + r'\b', full_text):
            # Normalize display name
            disp = tech.replace("\\", "")
            if disp not in state.technical_skills:
                state.technical_skills.append(disp)

    # 3. Seniority level extraction
    # Check for direct mentions
    for key, val in SENIORITY_KEYWORDS.items():
        if re.search(r'\b' + key + r'\b', full_text):
            state.seniority = val
            break
            
    # Also extract years of experience if mentioned
    years_match = re.search(r'(\d+)\s*years?(?:\s+of\s+experience)?', full_text)
    if years_match:
        years = int(years_match.group(1))
        if years >= 12:
            state.seniority = "Executive"
        elif years >= 7:
            state.seniority = "Director"
        elif years >= 5:
            state.seniority = "Senior"
        elif years >= 2:
            state.seniority = "Mid-Professional"
        else:
            state.seniority = "Entry-Level"

    # 4. Assessment style flags
    for word in PERSONALITY_KEYWORDS:
        if word in full_text:
            state.needs_personality = True
            break
            
    for word in COGNITIVE_KEYWORDS:
        if word in full_text:
            state.needs_cognitive = True
            break

    # 5. Compare requests (only on the last user message to avoid permanent state lock)
    if user_inputs:
        last_user_lower = user_inputs[-1]
        compare_match = re.findall(r'\bcompare\b|difference|versus|vs', last_user_lower)
        if compare_match:
            # Match actual assessment names from the catalog using exact or shorthand mapping
            short_hands = {
                "opq": "Occupational Personality Questionnaire OPQ32r",
                "opq32r": "Occupational Personality Questionnaire OPQ32r",
                "dsi": "Dependability and Safety Instrument (DSI)",
                "gsa": "Global Skills Assessment",
                "safety & dependability 8.0": "Manufac. & Indust. - Safety & Dependability 8.0",
                "safety & dependability": "Manufac. & Indust. - Safety & Dependability 8.0",
                "safety and dependability 8.0": "Manufac. & Indust. - Safety & Dependability 8.0",
                "safety and dependability": "Manufac. & Indust. - Safety & Dependability 8.0",
                "opq mq sales report": "OPQ MQ Sales Report",
                "sales report": "OPQ MQ Sales Report",
                "global skills assessment": "Global Skills Assessment",
                "global skills development report": "Global Skills Development Report",
                "sales transformation 2.0": "Sales Transformation 2.0 - Individual Contributor"
            }
            for sh, full_name in short_hands.items():
                if sh in last_user_lower:
                    if full_name not in state.compare_request:
                        state.compare_request.append(full_name)
            
            # Dynamic fallback: check actual catalog names if no shorthands match
            if not state.compare_request:
                catalog_names = _get_catalog_names()
                for name in catalog_names:
                    if name.lower() in last_user_lower:
                        if name not in state.compare_request:
                            state.compare_request.append(name)

    # 6. Refinements
    # Look for incremental triggers like "actually", "add", "remove", "instead", "also"
    refine_match = re.findall(r'\b(?:actually|instead|add|also|remove|except)\b', full_text)
    if refine_match:
        state.refinement_constraints.append("user updated constraints")

    return state


def prioritize_question(state: ConversationState) -> str:
    """
    Determines if any key information is missing, prioritizing questions.
    Returns the target parameter name that needs clarification, or None if complete.
    """
    # Generic words that the regex may extract as a "role" but are not actual roles.
    # If role_title is only one of these words, treat it as if no role was given.
    GENERIC_ROLE_WORDS = {
        "assessment", "assessments", "test", "tests", "solution", "solutions",
        "evaluation", "evaluations", "tool", "tools", "something", "one", "help",
        "advice", "recommendation", "recommendations", "battery", "batteries",
    }

    # 1. Check Role — only count it if it's a real role title, not a generic term
    raw_role = (state.role_title or "").lower().strip()
    has_role = bool(raw_role) and raw_role not in GENERIC_ROLE_WORDS

    # 2. Check Technical Skill
    has_skills = bool(state.technical_skills)

    # 3. Check Assessment Type
    has_assessment_type = state.needs_personality or state.needs_cognitive

    # 4. Check Hiring Domain
    has_domain = False
    DOMAIN_KEYWORDS = ["sales", "retail", "healthcare", "medical", "admin", "manufacturing", "industrial", "plant", "customer service", "call center", "finance", "analyst", "engineering"]
    if state.role_title:
        role_lower = state.role_title.lower()
        if any(domain in role_lower for domain in DOMAIN_KEYWORDS):
            has_domain = True

    # If we have at least one of these four matching signals, we are ready to retrieve and recommend
    if has_role or has_skills or has_domain or has_assessment_type:
        return None

    # Otherwise, we ask for clarification on the role_title
    return "role_title"
