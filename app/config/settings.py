from typing import Dict
from datetime import datetime

class Settings:
    DEFAULT_WEIGHTS: Dict[str, float] = {
        "skills_match": 0.35,
        "experience": 0.25,
        "education": 0.20,
        "certifications": 0.10,
        "location": 0.10
    }

    DEFAULT_PRIORITY = [
        "skills_match",
        "experience",
        "education",
        "certifications",
        "location"
    ]

    SUPPORTED_MODELS = {
        "gpt-4o": "openai",
        "gpt-4o-mini": "openai",
    }

