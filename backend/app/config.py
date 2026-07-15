"""Environment-driven config for the C3 PoC backend."""
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./c3.db")
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-insecure-secret")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
ALLOWED_LOGIN_DOMAIN = os.getenv("ALLOWED_LOGIN_DOMAIN", "")

GCMS_GRAPHQL_ENDPOINT = os.getenv("GCMS_GRAPHQL_ENDPOINT", "")
GCMS_USERNAME = os.getenv("GCMS_USERNAME", "")
GCMS_PASSWORD = os.getenv("GCMS_PASSWORD", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
COPILOT_MODEL = os.getenv("COPILOT_MODEL", "claude-sonnet-5")
SECRETS_KEY = os.getenv("SECRETS_KEY", "")  # Fernet key; production -> KMS/secrets manager
