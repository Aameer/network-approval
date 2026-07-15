"""Copilot chat endpoint."""
from fastapi import APIRouter
from pydantic import BaseModel

from ..services import copilot

router = APIRouter(prefix="/api/copilot", tags=["copilot"])


class Msg(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[Msg]


@router.post("/chat")
def chat(req: ChatRequest):
    return copilot.chat([m.model_dump() for m in req.messages])
