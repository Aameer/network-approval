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
OAUTH_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI", "http://localhost:3000/api/auth/google/callback")
ADMIN_EMAILS = [e.strip() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()]
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# Real traffic (GA4 export in BigQuery)
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
GA4_BQ_PROJECT = os.getenv("GA4_BQ_PROJECT", "")

# Inbox parser (IMAP) — the holding-co mailbox that receives network approval emails
PARSER_IMAP_HOST = os.getenv("PARSER_IMAP_HOST", "imap.gmail.com")
PARSER_EMAIL = os.getenv("PARSER_EMAIL", "")
PARSER_PASSWORD = os.getenv("PARSER_PASSWORD", "")

GCMS_GRAPHQL_ENDPOINT = os.getenv("GCMS_GRAPHQL_ENDPOINT", "")
GCMS_USERNAME = os.getenv("GCMS_USERNAME", "")
GCMS_PASSWORD = os.getenv("GCMS_PASSWORD", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
COPILOT_MODEL = os.getenv("COPILOT_MODEL", "claude-sonnet-5")
SECRETS_KEY = os.getenv("SECRETS_KEY", "")  # Fernet key; production -> KMS/secrets manager
