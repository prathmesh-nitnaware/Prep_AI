"""
backend/services/ai/pricing.py
==============================
Centralized AI Pricing, Pricing Versioning & Reproducibility,
Request-Specific Output Token Limits, and Prompt Versioning for PrepAI.
"""
import os
from typing import Dict, Tuple, Optional, Any

# =====================================================================
# 1. CENTRALIZED MODEL PRICING (Per 1 Million Tokens) & VERSIONING
# =====================================================================
AI_MODEL_PRICING: Dict[str, Dict[str, Any]] = {
    "gemini-2.0-flash": {
        "pricing_version": "google_gemini_2026_01",
        "effective_date": "2026-01-01",
        "input_per_million": float(os.getenv("GEMINI_2_FLASH_INPUT_PRICE_PER_M", "0.10")),
        "output_per_million": float(os.getenv("GEMINI_2_FLASH_OUTPUT_PRICE_PER_M", "0.40")),
    },
    "gemini-1.5-flash": {
        "pricing_version": "google_gemini_1_5_2026_01",
        "effective_date": "2026-01-01",
        "input_per_million": float(os.getenv("GEMINI_1_5_FLASH_INPUT_PRICE_PER_M", "0.075")),
        "output_per_million": float(os.getenv("GEMINI_1_5_FLASH_OUTPUT_PRICE_PER_M", "0.30")),
    },
    "gemini-1.5-pro": {
        "pricing_version": "google_gemini_1_5_pro_2026_01",
        "effective_date": "2026-01-01",
        "input_per_million": float(os.getenv("GEMINI_1_5_PRO_INPUT_PRICE_PER_M", "1.25")),
        "output_per_million": float(os.getenv("GEMINI_1_5_PRO_OUTPUT_PRICE_PER_M", "5.00")),
    },
    "ollama": {
        "pricing_version": "ollama_local_v1",
        "effective_date": "2026-01-01",
        "input_per_million": 0.0,
        "output_per_million": 0.0,
    },
    "fallback": {
        "pricing_version": "fallback_heuristic_v1",
        "effective_date": "2026-01-01",
        "input_per_million": 0.0,
        "output_per_million": 0.0,
    },
}

# Default fallback pricing if an unlisted model is specified
DEFAULT_MODEL_PRICING: Dict[str, Any] = {
    "pricing_version": "default_standard_2026_01",
    "effective_date": "2026-01-01",
    "input_per_million": float(os.getenv("DEFAULT_AI_INPUT_PRICE_PER_M", "0.10")),
    "output_per_million": float(os.getenv("DEFAULT_AI_OUTPUT_PRICE_PER_M", "0.40")),
}


def get_model_pricing_metadata(model_name: Optional[str]) -> Dict[str, Any]:
    """
    Resolves the full pricing definition and metadata for a given model.
    Guarantees reproducible historical calculations.
    """
    if not model_name:
        return DEFAULT_MODEL_PRICING

    clean_model = model_name.lower().strip()
    if clean_model.startswith("ollama") or "ollama" in clean_model:
        return AI_MODEL_PRICING["ollama"]
    if clean_model.startswith("fallback") or "fallback" in clean_model:
        return AI_MODEL_PRICING["fallback"]

    for key, pricing in AI_MODEL_PRICING.items():
        if key in clean_model:
            return pricing

    return DEFAULT_MODEL_PRICING


def get_model_pricing(model_name: Optional[str]) -> Dict[str, Any]:
    """Compatibility alias for get_model_pricing_metadata."""
    return get_model_pricing_metadata(model_name)


def calculate_token_cost(
    model_name: Optional[str],
    input_tokens: Optional[int],
    output_tokens: Optional[int],
    custom_pricing: Optional[Dict[str, Any]] = None,
) -> Tuple[float, float, float]:
    """
    Calculates exact (input_cost, output_cost, total_cost) from actual usage metadata.
    Returns values as rounded floats (6 decimal precision).
    """
    if not input_tokens and not output_tokens:
        return 0.0, 0.0, 0.0

    in_cnt = max(0, int(input_tokens or 0))
    out_cnt = max(0, int(output_tokens or 0))

    pricing = custom_pricing or get_model_pricing_metadata(model_name)
    input_cost = (in_cnt / 1_000_000.0) * float(pricing["input_per_million"])
    output_cost = (out_cnt / 1_000_000.0) * float(pricing["output_per_million"])
    total_cost = input_cost + output_cost

    return round(input_cost, 6), round(output_cost, 6), round(total_cost, 6)


# =====================================================================
# 2. REQUEST-SPECIFIC OUTPUT TOKEN LIMITS (Phase 9)
# =====================================================================
MAX_OUTPUT_TOKENS: Dict[str, int] = {
    "QUESTION_GENERATION": int(os.getenv("MAX_OUTPUT_TOKENS_QUESTIONS", "1024")),
    "ADAPTIVE_QUESTION": int(os.getenv("MAX_OUTPUT_TOKENS_ADAPTIVE_Q", "350")),
    "ANSWER_EVALUATION": int(os.getenv("MAX_OUTPUT_TOKENS_EVAL", "350")),
    "FINAL_REPORT": int(os.getenv("MAX_OUTPUT_TOKENS_REPORT", "512")),
    "RESUME_SCORING": int(os.getenv("MAX_OUTPUT_TOKENS_RESUME", "1500")),
    "CODING_EVALUATION": int(os.getenv("MAX_OUTPUT_TOKENS_CODING", "350")),
    "CHATBOT_ASSIST": int(os.getenv("MAX_OUTPUT_TOKENS_CHAT", "200")),
}


def get_max_output_tokens(request_type: str) -> int:
    """Returns the strict output token limit for a specific request type."""
    return MAX_OUTPUT_TOKENS.get(request_type, 512)


# =====================================================================
# 3. PROMPT VERSIONING (Phase 10)
# =====================================================================
PROMPT_VERSIONS: Dict[str, str] = {
    "QUESTION_GENERATION": "question_generation_v2",
    "ADAPTIVE_QUESTION": "adaptive_question_v1",
    "ANSWER_EVALUATION": "answer_evaluation_v2",
    "FINAL_REPORT": "final_report_v2",
    "RESUME_SCORING": "resume_scoring_v2",
    "CODING_EVALUATION": "coding_evaluation_v2",
    "CHATBOT_ASSIST": "chatbot_assist_v2",
}


def get_prompt_version(request_type: str) -> str:
    """Returns the prompt version identifier for telemetry tracking."""
    return PROMPT_VERSIONS.get(request_type, "v2")
