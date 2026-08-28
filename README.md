# ORCA Prototype - Setup & Run

## What this is
A working demo of the ORCA agent flow:
Planner -> Weather Agent -> Ocean Agent -> Risk Agent -> Geospatial Agent -> Synthesis Agent,
built with LangGraph, using mock JSON data for Kochi, Chennai, and Visakhapatnam
(standing in for live INCOIS/MOSDAC feeds).

## 1. Backend setup
```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Optional: enable real AI-generated answers
Without this, the app still works fully using a rule-based fallback answer.
```bash
export ANTHROPIC_API_KEY=your_key_here      # on Windows: set ANTHROPIC_API_KEY=your_key_here
```

### Run the backend
```bash
uvicorn main:app --reload --port 8000
```
Check it's alive: open http://localhost:8000 in a browser - you should see
`{"status": "ORCA backend is running"}`

## 2. Frontend
Just open `frontend/index.html` directly in a browser (double-click it,
or right-click -> Open with browser). No build step needed.

Make sure the backend is running first, or the chat will show a connection error.

## 3. Try these demo queries
- "Is it safe to fish tomorrow near Kochi?" -> should show SAFE
- "Should I go to sea near Chennai today?" -> should show UNSAFE (cyclone + high waves)
- "What are the conditions near Visakhapatnam?" -> should show SAFE

## 4. Adding more locations
Edit `backend/data/marine_data.json` - just add another key like `"alibaug": {...}`
following the same structure as the existing entries. No code changes needed.

## 5. If something breaks right before the demo
- Backend won't start -> check you're in the `backend` folder and venv is activated
- Frontend shows "could not reach backend" -> confirm uvicorn is still running in a terminal
- LLM answer looks broken -> the app automatically falls back to a rule-based answer,
  so this should never fully break the demo. If it feels less polished, that's expected
  without ANTHROPIC_API_KEY set.
- Take a screen recording of a successful run as a backup in case live wifi/API fails
  during the actual pitch.

## What to say about the architecture in your pitch
"Planner, Weather, Ocean, Risk, and Geospatial agents are orchestrated with LangGraph.
For tonight's prototype we use a mock dataset standing in for live ISRO/INCOIS feeds,
and a lightweight JSON store instead of PostgreSQL+PostGIS - both are the natural
next step for a production version, prioritized correctly to prove the agentic
architecture works first."