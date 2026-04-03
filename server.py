import os
import json
import uuid
import re
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from groq import Groq

# ── Config ────────────────────────────────────────────
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise EnvironmentError(
        "GROQ_API_KEY environment variable is not set. "
        "Run: set GROQ_API_KEY=your_key_here"
    )

LLM_MODEL = "llama-3.3-70b-versatile"
client = Groq(api_key=GROQ_API_KEY)

# ── FastAPI App ───────────────────────────────────────
app = FastAPI(title="Voice Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the frontend folder at root
app.mount("/static", StaticFiles(directory="."), name="static")

@app.get("/")
def serve_frontend():
    return FileResponse("index.html")

# ── Mock Database ─────────────────────────────────────
MOCK_ORDERS = {
    "1001": {"order_id": "1001", "item": "Wireless Headphones", "status": "Out for delivery", "eta": "Today by 7 PM", "placed_on": "2025-04-01", "customer": "Rahul Sharma"},
    "1002": {"order_id": "1002", "item": "Running Shoes", "status": "Shipped", "eta": "April 5, 2025", "placed_on": "2025-03-30", "customer": "Priya Singh"},
    "1003": {"order_id": "1003", "item": "Laptop Stand", "status": "Processing", "eta": "April 7, 2025", "placed_on": "2025-04-02", "customer": "Amit Verma"},
}

COMPLAINTS_LOG: list = []

# ── Session Store ─────────────────────────────────────
SESSION_STORE: dict = {}

def create_session() -> str:
    session_id = str(uuid.uuid4())
    SESSION_STORE[session_id] = {
        "history": [],
        "intent": None,
        "slots": {},
        "language": "en",
        "sentiment_scores": [],
        "resolved": False,
    }
    return session_id

def get_session(session_id: str) -> dict:
    session = SESSION_STORE.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found or expired.")
    return session

def add_turn(session_id: str, role: str, content: str) -> None:
    SESSION_STORE[session_id]["history"].append({"role": role, "content": content})

# ── Business Logic ────────────────────────────────────
def get_order_status(order_id: str) -> dict:
    order = MOCK_ORDERS.get(order_id.strip())
    if not order:
        return {"success": False, "message": f"Order {order_id} not found"}
    return {"success": True, "data": order}

def register_complaint(session_id: str, description: str) -> dict:
    ticket_id = f"TKT-{uuid.uuid4().hex[:6].upper()}"
    COMPLAINTS_LOG.append({
        "ticket_id": ticket_id,
        "session_id": session_id,
        "description": description,
        "timestamp": datetime.now().isoformat(),
    })
    return {"success": True, "ticket_id": ticket_id}

# ── Prompt ────────────────────────────────────────────
def build_system_prompt(session: dict) -> str:
    return f"""You are a multilingual customer support voice agent for an e-commerce platform.

LANGUAGE RULES:
- Detect the language the customer is using: Hindi, English, or Hinglish.
- ALWAYS reply in the EXACT same language the customer used.
- Keep replies SHORT — max 2 sentences. This is a phone call.

YOUR RESPONSE MUST ALWAYS HAVE TWO PARTS IN THIS EXACT ORDER:

PART 1 — A JSON block (no markdown, no backticks):
{{
"intent": "order_status" or "complaint" or "unclear",
"slots": {{
    "order_id": "the order number if customer mentioned it, else null",
    "complaint_description": "short English summary of complaint if any, else null"
}},
"language": "en" or "hi" or "hinglish",
"sentiment": "neutral" or "frustrated"
}}

PART 2 — The spoken reply on a new line starting with REPLY:
REPLY: <your spoken response to the customer>

IMPORTANT RULES:
- Output the raw JSON first, then REPLY: on a new line.
- Do NOT wrap JSON in backticks or markdown.
- If intent is order_status and order_id is not yet known, ask for it.
- If intent is complaint and no description yet, ask what the problem is.
- Extract order_id even if customer says "mera order 1001 hai".
- Currently known slots: {json.dumps(session.get("slots", {}))}
"""

# ── Parser ────────────────────────────────────────────
def parse_llm_output(raw: str) -> tuple[dict, str]:
    raw = re.sub(r"```(?:json)?", "", raw).strip()
    parsed: dict = {}
    reply: str = ""
    end: int = 0

    try:
        start = raw.index("{")
        depth = 0
        end = start
        for i, ch in enumerate(raw[start:], start=start):
            if ch == "{": depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        parsed = json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        pass

    if "REPLY:" in raw:
        reply = raw.split("REPLY:")[-1].strip()
    elif parsed and end:
        after_json = raw[end:].strip()
        reply = after_json if after_json else raw.strip()
    else:
        reply = raw.strip()

    if not parsed:
        parsed = {"intent": "unclear", "slots": {"order_id": None, "complaint_description": None}, "language": "en", "sentiment": "neutral"}

    if parsed.get("intent") == "order_status":
        slots = parsed.get("slots", {})
        if not slots.get("order_id"):
            match = re.search(r"\b(\d{3,6})\b", reply)
            if match:
                parsed["slots"]["order_id"] = match.group(1)

    return parsed, reply

# ── LLM Call ──────────────────────────────────────────
def call_llm(session: dict, user_message: str) -> tuple[dict, str]:
    messages = [{"role": "system", "content": build_system_prompt(session)}]
    messages += session["history"]
    messages.append({"role": "user", "content": user_message})
    response = client.chat.completions.create(model=LLM_MODEL, messages=messages, temperature=0.3, max_tokens=400)
    return parse_llm_output(response.choices[0].message.content)

# ── Core Turn Logic ───────────────────────────────────
def process_turn(session_id: str, user_input: str) -> dict:
    session = get_session(session_id)

    if session.get("intent") == "order_status" and not session["slots"].get("order_id"):
        match = re.fullmatch(r"\s*(\d{3,6})\s*", user_input)
        if match:
            session["slots"]["order_id"] = match.group(1)

    add_turn(session_id, "user", user_input)
    parsed, reply = call_llm(session, user_input)

    intent    = parsed.get("intent", "unclear")
    slots     = parsed.get("slots", {})
    language  = parsed.get("language", "en")
    sentiment = parsed.get("sentiment", "neutral")

    if intent != "unclear":
        session["intent"] = intent
    session["language"] = language
    session["sentiment_scores"].append(sentiment)

    for k, v in slots.items():
        if v and v != "null":
            session["slots"][k] = v

    api_result = None
    if session["intent"] == "order_status":
        order_id = session["slots"].get("order_id")
        if order_id:
            api_result = get_order_status(str(order_id))
    elif session["intent"] == "complaint":
        desc = session["slots"].get("complaint_description")
        if desc:
            api_result = register_complaint(session_id, desc)

    if api_result:
        lang = session["language"]
        final_prompt = (
            f"[SYSTEM: API returned this result: {json.dumps(api_result)}. "
            f"Generate the final spoken reply to the customer in language='{lang}'. "
            f"Do NOT output JSON this time. Just the spoken reply in max 2 sentences.]"
        )
        add_turn(session_id, "user", final_prompt)
        final_response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "system", "content": build_system_prompt(session)}, *session["history"]],
            temperature=0.3, max_tokens=150,
        )
        reply = final_response.choices[0].message.content.strip()
        if "REPLY:" in reply:
            reply = reply.split("REPLY:")[-1].strip()
        session["history"].pop()
        if api_result.get("success"):
            session["resolved"] = True

    add_turn(session_id, "assistant", reply)

    escalate = False
    scores = session["sentiment_scores"]
    if len(scores) >= 2 and all(s == "frustrated" for s in scores[-2:]):
        escalate = True

    return {
        "reply": reply,
        "intent": session["intent"],
        "language": session["language"],
        "sentiment": sentiment,
        "resolved": session["resolved"],
        "escalate": escalate,
        "slots": session["slots"],
    }

# ── API Routes ────────────────────────────────────────
@app.post("/session/new")
def new_session():
    session_id = create_session()
    return {"session_id": session_id}

class ChatRequest(BaseModel):
    session_id: str
    message: str

@app.post("/chat")
def chat(req: ChatRequest):
    return process_turn(req.session_id, req.message)

@app.get("/session/{session_id}/info")
def session_info(session_id: str):
    session = get_session(session_id)
    return {
        "intent": session["intent"],
        "slots": session["slots"],
        "language": session["language"],
        "sentiment_scores": session["sentiment_scores"],
        "resolved": session["resolved"],
        "turn_count": len([m for m in session["history"] if m["role"] == "user"]),
    }

# ── Run ───────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
