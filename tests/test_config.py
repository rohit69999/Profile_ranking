import pytest
import os
from dotenv import load_dotenv

@pytest.fixture(autouse=True)
def env_setup():
    """Automatically load environment variables for all tests"""
    load_dotenv()
    
    # Set test API keys
    os.environ["OPENAI_API_KEY"] = "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"
    os.environ["GROQ_API_KEY"] = "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"
    os.environ["LLAMA_CLOUD_API_KEY"] = "llx-lsscLDnezIubtE2iWewd0iywy7xjEuynDti9mCOKFQvBzjq2"
    
@pytest.fixture
def sample_scoring_weights():
    return {
        "skills_match": 0.35,
        "experience": 0.25,
        "education": 0.20,
        "certifications": 0.10,
        "location": 0.10
    }

@pytest.fixture
def sample_ranking_priority():
    return [
        "skills_match",
        "experience", 
        "education",
        "certifications",
        "location"
    ]