import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env (override system env to reflect disk changes)
load_dotenv(override=True)

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = BASE_DIR / "backend"
FRONTEND_DIR = BASE_DIR / "frontend"
DATA_DIR = BASE_DIR / "data"

# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Groq API Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_SIMPLE_MODEL = os.getenv("GROQ_SIMPLE_MODEL", "llama-3.1-8b-instant")
GROQ_HEAVY_MODEL = os.getenv("GROQ_HEAVY_MODEL", "llama-3.3-70b-versatile")

# Azure OpenAI Configuration
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "https://zach-resource.services.ai.azure.com/openai/v1")
AZURE_OPENAI_MODEL = os.getenv("AZURE_OPENAI_MODEL", "gpt-5.6-sol")

# Legacy compatibility exports if referenced elsewhere
EXHAUSTED_MODELS = set()
