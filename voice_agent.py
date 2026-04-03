import os
import json
import uuid
import re
from datetime import datetime
from groq import Groq

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise EnvironmentError("Set GROQ_API_KEY")

LLM_MODEL = "llama-3.3-70b-versatile"
client = Groq(api_key=GROQ_API_KEY)

# ---------------- MOCK DATA ---------------- #

MOCK_ORDERS = {
    "1001": {"order_id": "1001", "item": "Wireless Headphones", "status": "Out for delivery", "eta": "Today by 7 PM"},
    "1002": {"order_id": "1002", "item": "Running Shoes", "status": "Shipped", "eta": "April 5"},
    "1003": {"order_id": "1003", "item": "Laptop Stand", "status": "Processing", "eta": "April 7"},
}

def get_order_status(order_id: str):
    order = MOCK_ORDERS.get(order_id.strip())
    return {"success": True, "data": order} if order else {"success": False, "message": "Order not found"}

COMPLAINTS_LOG = []

def register_complaint(session_id: str, description: str):
    ticket_id = f"TKT-{uuid.uuid4().hex[:6].upper()}"
    COMPLAINTS_LOG.append({
        "ticket_id": ticket_id,
        "session_id": session_id,
        "description": description,
        "time": datetime.now().isoformat(),
    })
    return {"success": True, "ticket_id": ticket_id}

# ---------------- SESSION ---------------- #

SESSION_STORE = {}

def create_session():
    sid = str(uuid.uuid4())
    SESSION_STORE[sid] = {
        "history": [],
        "intent": None,
        "slots": {},
        "language": "en",
        "sentiment": [],
        "resolved": False
    }
    return sid

def get_session(sid):
    if sid not in SESSION_STORE:
        raise KeyError("Session expired")
    return SESSION_STORE[sid]

def add_turn(sid, role, content):
    hist = SESSION_STORE[sid]["history"]
    hist.append({"role": role, "content": content})
    if len(hist) > 10:
        SESSION_STORE[sid]["history"] = hist[-10:]

# ---------------- PROMPTS ---------------- #

def build_prompt(session):
    return f"""
You are a multilingual customer support agent.

Return:
1. JSON
2. Then plain reply

JSON:
{{
"intent": "order_status" or "complaint" or "unclear",
"slots": {{
"order_id": null,
"complaint_description": null
}},
"language": "en" or "hi" or "hinglish",
"sentiment": "neutral" or "frustrated"
}}

Rules:
- Keep reply max 2 sentences
- Same language as user
- Known slots: {json.dumps(session["slots"])}
"""

def build_final_prompt(session, api_result):
    return f"""
You are a support agent.

Respond in {session["language"]}.
Max 2 sentences.
No JSON.

API RESULT:
{json.dumps(api_result)}
"""

# ---------------- PARSER ---------------- #

def parse_output(raw):
    raw = raw.strip()

    parsed = {}
    reply = ""

    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
        except:
            pass

    if "REPLY:" in raw:
        reply = raw.split("REPLY:")[-1].strip()
    else:
        reply = raw.replace(match.group(), "").strip() if match else raw

    if not parsed:
        parsed = {
            "intent": "unclear",
            "slots": {"order_id": None, "complaint_description": None},
            "language": "en",
            "sentiment": "neutral"
        }

    return parsed, reply

# ---------------- CORE ---------------- #

def call_llm(messages):
    res = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        temperature=0.3,
        max_tokens=300
    )
    return res.choices[0].message.content

def process_turn(sid, user_input):

    if len(user_input.strip()) < 2:
        return "Hello, how can I help you?"

    session = get_session(sid)

    # extract order id directly
    match = re.search(r"\b(\d{3,6})\b", user_input)
    if match:
        session["slots"]["order_id"] = match.group(1)

    add_turn(sid, "user", user_input)

    messages = [{"role": "system", "content": build_prompt(session)}, *session["history"]]

    raw = call_llm(messages)
    parsed, reply = parse_output(raw)

    intent = parsed.get("intent", "unclear")
    slots = parsed.get("slots", {})
    lang = parsed.get("language", "en")

    if lang not in ["en", "hi", "hinglish"]:
        lang = "en"

    if intent != "unclear":
        session["intent"] = intent

    session["language"] = lang

    for k, v in slots.items():
        if v not in (None, "null", "", "None"):
            session["slots"][k] = v

    # ---------------- API CALL ---------------- #

    api_result = None

    if session["intent"] == "order_status":
        oid = session["slots"].get("order_id")
        if oid:
            api_result = get_order_status(oid)

    elif session["intent"] == "complaint":
        desc = session["slots"].get("complaint_description")
        if desc:
            api_result = register_complaint(sid, desc)

    # ---------------- FINAL RESPONSE ---------------- #

    if api_result:
        final_messages = [
            {"role": "system", "content": build_final_prompt(session, api_result)},
            *session["history"]
        ]

        reply = call_llm(final_messages).strip()

        session["resolved"] = api_result.get("success", False)

    # cleanup for TTS
    reply = reply.replace("REPLY:", "").strip()

    if not reply:
        reply = "Sorry, I didn't understand. Can you repeat?"

    add_turn(sid, "assistant", reply)

    return reply

# ---------------- INTERFACE ---------------- #

def run():
    sid = create_session()
    print("Agent: Hello! How can I help you?\n")

    while True:
        user = input("You: ")

        if user.lower() in ["exit", "quit"]:
            print("Agent: Goodbye!")
            break

        reply = process_turn(sid, user)
        print("Agent:", reply, "\n")

if __name__ == "__main__":
    run()