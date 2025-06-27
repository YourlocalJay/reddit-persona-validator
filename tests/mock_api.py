from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
import random

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/v1/chat/completions")
async def mock_deepseek(request: dict):
    trust_level = "high" if random.random() > 0.5 else "medium"
    
    return {
        "choices": [{
            "message": {
                "content": json.dumps({
                    "viability_score": 92 if trust_level == "high" else 65,
                    "best_use_case": ["CPA"] if trust_level == "high" else ["Community"],
                    "risk_factors": [],
                    "next_review_date": (
                        datetime.now() + 
                        timedelta(days=30 if trust_level == "high" else 7)
                    ).strftime('%Y-%m-%d')
                }),
                "role": "assistant"
            }
        }]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
