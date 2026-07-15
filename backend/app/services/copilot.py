"""C3 copilot — a bounded Claude tool-use loop over the read tools.

PoC scope: read-only. The copilot answers portfolio questions by calling tools; it
cannot act yet. When act tools land, they route through the approval gate, not here.
"""
from __future__ import annotations

import json

from ..config import ANTHROPIC_API_KEY, COPILOT_MODEL
from .tools import DISPATCH, TOOLS

SYSTEM = (
    "You are the C3 copilot — the assistant inside Curatte's Central Command & Control "
    "console. You help internal operators understand the site portfolio and its affiliate-"
    "network approval status. Use the tools to fetch real data; never invent site names, "
    "statuses, or publisher IDs. Be concise and concrete. If asked to *do* something "
    "(apply, change status), explain that acting is coming next and is gated by approval — "
    "for now you can READ, and you can PROPOSE an application with apply_to_network — "
    "that creates a gated dry-run a human approves in the console; you cannot approve or "
    "submit yourself. The 3 sandbox sites are dailyreviewtoday.com (MUX), "
    "saversheaven.com, and dailyessentialstips.com; the live PoC target is applying "
    "dailyreviewtoday to SourceKnowledge."
)

MAX_STEPS = 6


def chat(messages: list[dict]) -> dict:
    """messages: [{role:'user'|'assistant', content:str}]. Returns {reply, tools_used}."""
    if not ANTHROPIC_API_KEY:
        return {"reply": None,
                "error": "ANTHROPIC_API_KEY not set in backend/.env — copy it from coupon-engine/.env.",
                "tools_used": []}
    import anthropic  # imported lazily so the app boots without the dep during early setup

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    convo = [{"role": m["role"], "content": m["content"]} for m in messages]
    tools_used = []

    for _ in range(MAX_STEPS):
        resp = client.messages.create(
            model=COPILOT_MODEL, max_tokens=1024, system=SYSTEM, tools=TOOLS, messages=convo,
        )
        if resp.stop_reason == "tool_use":
            convo.append({"role": "assistant", "content": [b.model_dump() for b in resp.content]})
            results = []
            for block in resp.content:
                if block.type == "tool_use":
                    fn = DISPATCH.get(block.name)
                    out = fn(**(block.input or {})) if fn else {"error": f"unknown tool {block.name}"}
                    tools_used.append({"tool": block.name, "input": block.input})
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(out),
                    })
            convo.append({"role": "user", "content": results})
            continue

        text = "".join(b.text for b in resp.content if b.type == "text")
        return {"reply": text, "tools_used": tools_used}

    return {"reply": "(stopped after the max tool-call budget)", "tools_used": tools_used}
