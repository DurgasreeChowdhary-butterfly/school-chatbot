"""School chatbot backend. Start with: uvicorn backend.app.main:app --reload"""
import os

from dotenv import load_dotenv
from fastapi import FastAPI

# Read settings from the .env file in the project folder.
load_dotenv()

# DEMO_MODE=true means kb/ holds dummy content. Defaults to true to stay safe.
DEMO_MODE = os.getenv("DEMO_MODE", "true").strip().lower() == "true"

app = FastAPI(title="School Chatbot")


@app.get("/health")
def health():
    """Quick check that the server is running."""
    return {"status": "ok", "demo": DEMO_MODE}
