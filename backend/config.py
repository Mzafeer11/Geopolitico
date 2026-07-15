import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = BASE_DIR / "backend"
FRONTEND_DIR = BASE_DIR / "frontend"
DATA_DIR = BASE_DIR / "data"

# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

# GitHub Models API configuration
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_API_URL = "https://models.github.ai/inference"

GITHUB_MODELS = [
    "openai/gpt-5",
    "openai/gpt-5-mini",
    "openai/gpt-5-nano",
    "openai/gpt-4.1-nano",
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "openai/meta/Llama-3.3-70B-Instruct",
    "openai/deepseek/DeepSeek-R1",
    "openai/microsoft/Phi-4",
    "openai/xai/grok-3-mini",
    "openai/mistral-ai/mistral-small-2503",
]


# Set of exhausted models (rate-limited) during runtime
EXHAUSTED_MODELS = set()
