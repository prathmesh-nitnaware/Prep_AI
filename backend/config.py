import os
from dotenv import load_dotenv

load_dotenv()


def parse_bool(value, default: bool = False) -> bool:
    """
    Strictly parse a boolean environment variable.
    Only explicit truthy values ('true', '1', 'yes', 'on', True, 1) evaluate to True.
    Invalid, unaccepted, or empty values strictly evaluate to False (or default if None).
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    normalized = str(value).strip().lower()
    return normalized in ("true", "1", "yes", "on")


def parse_proxy_strategy(raw_val: any) -> str:
    """
    Parse and validate the reverse proxy client IP resolution strategy.
    Accepted strategies: 'direct', 'nginx', 'render'.
    Defaults safely to 'direct'. Emits a warning if an invalid strategy is specified.
    """
    valid_strategies = ("direct", "nginx", "render")
    if raw_val is None:
        return "direct"
    normalized = str(raw_val).strip().lower()
    if normalized in valid_strategies:
        return normalized

    import logging
    logging.getLogger("prepai").warning(
        "Invalid PROXY_STRATEGY configured; falling back to 'direct'"
    )
    return "direct"


class Config:
    ENVIRONMENT   = (os.getenv("ENVIRONMENT") or "development").strip().lower()

    # PIE (PrepAI Intelligence Engine) feature flag
    PIE_ENABLED   = parse_bool(os.getenv("PIE_ENABLED", "false"), default=False)

    # Reverse proxy client IP resolution strategy: 'direct', 'nginx', 'render'
    VALID_PROXY_STRATEGIES = ("direct", "nginx", "render")
    PROXY_STRATEGY        = parse_proxy_strategy(os.getenv("PROXY_STRATEGY", "direct"))

    DEFAULT_SECRET_KEY = "prepai_local_dev_secret_key_2026_minimum_32_bytes_long"
    SECRET_KEY    = os.getenv("SECRET_KEY", DEFAULT_SECRET_KEY)
    DATABASE_URL  = os.getenv("DATABASE_URL")          # Neon PostgreSQL connection string
    OLLAMA_HOST   = os.getenv("OLLAMA_HOST",  "http://127.0.0.1:11434")
    OLLAMA_MODEL  = os.getenv("OLLAMA_MODEL", "llama3:8b")
    GEMINI_MODEL            = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    GEMINI_QUESTION_MODEL   = os.getenv("GEMINI_QUESTION_MODEL", os.getenv("GEMINI_MODEL", "gemini-2.0-flash"))
    GEMINI_EVALUATION_MODEL = os.getenv("GEMINI_EVALUATION_MODEL", os.getenv("GEMINI_MODEL", "gemini-2.0-flash"))
    GEMINI_REPORT_MODEL     = os.getenv("GEMINI_REPORT_MODEL", os.getenv("GEMINI_MODEL", "gemini-2.0-flash"))
    MAX_AI_RETRIES          = int(os.getenv("MAX_AI_RETRIES", "2"))
    MAX_INTERVIEW_QUESTIONS = int(os.getenv("MAX_INTERVIEW_QUESTIONS", "10"))
    MAX_REPORT_GENERATIONS  = int(os.getenv("MAX_REPORT_GENERATIONS", "1"))

    # Email & Authentication Policy
    EMAIL_VERIFICATION_ENABLED = os.getenv("EMAIL_VERIFICATION_ENABLED", "False").lower() in ("true", "1", "t")
    MAIL_SERVER   = os.getenv("MAIL_SERVER",   "smtp.gmail.com")
    MAIL_PORT     = int(os.getenv("MAIL_PORT", 587))
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    MAIL_USE_TLS  = os.getenv("MAIL_USE_TLS", "True").lower() in ("true", "1", "t")
    FRONTEND_URL  = os.getenv("FRONTEND_URL",  "http://localhost:5173")

