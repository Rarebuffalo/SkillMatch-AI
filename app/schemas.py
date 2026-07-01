from typing import List, Optional
from pydantic import BaseModel, Field

class Message(BaseModel):
    role: str = Field(..., description="Role of the sender: user or assistant")
    content: str = Field(..., description="Content of the message")

class ChatRequest(BaseModel):
    messages: List[Message] = Field(..., description="List of messages representing the conversation history")

class Recommendation(BaseModel):
    name: str = Field(..., description="Exact name of the recommended assessment")
    url: str = Field(..., description="Exact URL of the assessment")
    test_type: str = Field(..., description="Assessment test type classification: K, P, or A")

class ChatResponse(BaseModel):
    reply: str = Field(..., description="The conversational agent response text")
    recommendations: List[Recommendation] = Field(default_factory=list, description="Shortlist of recommendations (1 to 10 items, or empty list)")
    end_of_conversation: bool = Field(default=False, description="True if the conversation is considered complete")

class ConversationState(BaseModel):
    role_title: str = Field(default="", description="The target hiring job role (e.g. Java developer)")
    technical_skills: List[str] = Field(default_factory=list, description="Target technical languages or skills")
    seniority: str = Field(default="", description="Seniority level target (e.g. Senior, Mid, Junior)")
    needs_personality: bool = Field(default=False, description="True if personality tests are requested")
    needs_cognitive: bool = Field(default=False, description="True if cognitive/aptitude tests are requested")
    compare_request: List[str] = Field(default_factory=list, description="Names of assessments requested for comparison")
    refinement_constraints: List[str] = Field(default_factory=list, description="Additional constraints added during conversation")
