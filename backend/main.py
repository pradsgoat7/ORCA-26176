from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agents import run_query

app = FastAPI(title="ORCA - Marine Intelligence Prototype")

# Allow the frontend (opened as a local file or on a different port) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    query: str


@app.get("/")
def health_check():
    return {"status": "ORCA backend is running"}


@app.post("/ask")
def ask(request: AskRequest):
    result = run_query(request.query)

    if result.get("error"):
        return {"answer": result["answer"], "error": result["error"]}

    return {
        "answer": result["answer"],
        "risk_level": result["risk"]["level"],
        "risk_reasons": result["risk"]["reasons"],
        "weather": result["weather"],
        "ocean": result["ocean"],
        "map": {
            "user_location": result["geospatial"]["location_coords"],
            "location_name": result["geospatial"]["location_name"],
            "nearest_pfz": result["geospatial"]["nearest_pfz"],
        },
    }