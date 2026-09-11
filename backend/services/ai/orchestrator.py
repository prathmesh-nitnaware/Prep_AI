"""
backend/services/ai/orchestrator.py
===================================
Interview Orchestrator, Deterministic Scoring Engine, and AI Telemetry Analytics.
Bridges Routes <-> Neon PostgreSQL <-> Deterministic Logic <-> GeminiService.
Ensures zero unnecessary AI calls, PostgreSQL row-level locking (FOR UPDATE)
for concurrency safety, failure fallback, pricing versioning, and real telemetry-based cost analytics.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from extensions import get_db, dict_cursor
from .gemini_service import gemini_service, AIResult
from .pricing import (
    calculate_token_cost,
    get_model_pricing_metadata,
    get_max_output_tokens,
    get_prompt_version,
)
from .router import model_router
from .prompts import (
    build_question_generation_prompt,
    build_adaptive_next_question_prompt,
    build_answer_evaluation_prompt,
    build_final_report_prompt,
    build_coding_evaluation_prompt,
    build_resume_analysis_prompt,
)
from .schemas import (
    validate_questions_output,
    validate_adaptive_question,
    validate_answer_evaluation,
    validate_final_report,
    validate_coding_evaluation,
    validate_resume_analysis,
)
from .exceptions import AIServiceError
from models.user_model import get_user_by_id

logger = logging.getLogger(__name__)


# =====================================================================
# 1. AI USAGE & TELEMETRY LOGGING (Pricing Governance & Reproducibility)
# =====================================================================

def record_ai_usage(
    request_type: str,
    result: Optional[AIResult] = None,
    interview_id: Optional[str] = None,
    user_id: Optional[str] = None,
    status: str = "success",
    latency_ms: int = 0,
    provider_latency_ms: Optional[int] = None,
    retry_delay_ms: int = 0,
    retries: int = 0,
    model: str = "unknown",
    provider: str = "gemini",
    prompt_version: Optional[str] = None,
    pricing_version: Optional[str] = None,
    pricing_effective_date: Optional[str] = None,
    input_price_per_million: Optional[float] = None,
    output_price_per_million: Optional[float] = None,
    input_cost: float = 0.0,
    output_cost: float = 0.0,
    estimated_cost: float = 0.0,
    cache_hit: bool = False,
    validation_failed: bool = False,
    truncation_detected: bool = False,
    conn: Optional[Any] = None,
) -> None:
    """
    Persists AI usage telemetry into Neon ai_usage table.
    Stores real token metadata, exact pricing version, and calculated costs.
    Reuses provided connection to avoid nested pool checkout.
    """
    try:
        in_tokens = result.usage.input_tokens if result else None
        out_tokens = result.usage.output_tokens if result else None
        tot_tokens = result.usage.total_tokens if result else None
        used_model = result.model_used if result else model
        used_provider = result.provider if result else provider
        prompt_ver = result.prompt_version if result else (prompt_version or get_prompt_version(request_type))
        req_latency = result.latency_ms if result else latency_ms
        prov_latency = result.provider_latency_ms if result else (provider_latency_ms or req_latency)
        ret_delay = result.retry_delay_ms if result else retry_delay_ms
        retry_cnt = result.retry_count if result else retries
        req_status = result.status if result else status
        is_cache_hit = result.cache_hit if result else cache_hit
        val_failed = result.validation_failed if result else validation_failed
        trunc_detected = result.truncation_detected if result else truncation_detected

        if result:
            p_ver = result.usage.pricing_version
            p_date = result.usage.pricing_effective_date
            in_p = result.usage.input_price_per_million
            out_p = result.usage.output_price_per_million
            in_c = result.usage.input_cost
            out_c = result.usage.output_cost
            tot_c = result.usage.estimated_cost
        else:
            meta = get_model_pricing_metadata(used_model)
            p_ver = pricing_version or meta.get("pricing_version", "google_gemini_2026_01")
            p_date = pricing_effective_date or meta.get("effective_date", "2026-01-01")
            in_p = input_price_per_million if input_price_per_million is not None else float(meta.get("input_per_million", 0.10))
            out_p = output_price_per_million if output_price_per_million is not None else float(meta.get("output_per_million", 0.40))
            
            in_c, out_c, tot_c = calculate_token_cost(
                used_model,
                in_tokens,
                out_tokens,
                custom_pricing={
                    "pricing_version": p_ver,
                    "effective_date": p_date,
                    "input_per_million": in_p,
                    "output_per_million": out_p,
                }
            )
            if estimated_cost > 0:
                tot_c = estimated_cost

        sql = """
            INSERT INTO ai_usage (
                interview_id, user_id, request_type, model, provider, prompt_version,
                pricing_version, pricing_effective_date, input_price_per_million, output_price_per_million,
                status, input_tokens, output_tokens, total_tokens,
                input_cost, output_cost, estimated_cost,
                latency_ms, provider_latency_ms, retry_delay_ms, retry_count,
                cache_hit, validation_failed, truncation_detected
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            interview_id,
            user_id,
            request_type,
            used_model,
            used_provider,
            prompt_ver,
            p_ver,
            p_date,
            in_p,
            out_p,
            req_status,
            in_tokens,
            out_tokens,
            tot_tokens,
            in_c,
            out_c,
            tot_c,
            req_latency,
            prov_latency,
            ret_delay,
            retry_cnt,
            is_cache_hit,
            val_failed,
            trunc_detected,
        )

        if conn is not None:
            with conn.cursor() as cur:
                cur.execute(sql, params)
        else:
            with get_db() as db_conn:
                with db_conn.cursor() as cur:
                    cur.execute(sql, params)
    except Exception as e:
        logger.warning(f"Failed to record AI usage telemetry: {e}")


# =====================================================================
# 2. DETERMINISTIC SCORING ENGINE
# =====================================================================

def calculate_interview_scores(questions: List[Dict[str, Any]], answers: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Authoritative, deterministic scoring engine for PrepAI.
    Strictly separates:
      1. Content / Job Performance Score (85% weight)
      2. Delivery / Communication Score (15% weight)
      3. Overall Hiring Score (Weighted combination)
      4. Evaluation Reliability (HIGH / MEDIUM / LOW based on telemetry and length)
      5. Session-Level Trends & Topic Breakdown
    """
    total_questions = len(questions)
    answered_questions = len(answers)
    skipped_questions = max(0, total_questions - answered_questions)
    completion_rate = round((answered_questions / max(1, total_questions)) * 100)

    if not answers:
        return {
            "overall_score": 0,
            "content_score": 0,
            "technical_score": 0.0,
            "delivery_score": 0,
            "clarity_score": 0.0,
            "confidence_score": 0.0,
            "evaluation_reliability": "LOW",
            "questions_total": total_questions,
            "questions_answered": 0,
            "questions_skipped": skipped_questions,
            "completion_percentage": 0,
            "top_strengths": [],
            "top_weaknesses": [],
            "content_dimensions": {
                "relevance": 0,
                "technical_accuracy": 0,
                "depth": 0,
                "completeness": 0,
                "reasoning": 0,
                "clarity": 0,
                "avg_depth_level": 0,
                "all_technical_errors": [],
            },
            "delivery_metrics": {
                "avg_wpm": 0,
                "total_words_spoken": 0,
                "total_filler_words": 0,
                "avg_filler_rate_pct": 0.0,
                "total_pauses": 0,
                "avg_face_presence_pct": 0,
                "avg_looking_away_pct": 0,
                "avg_posture_stability": 100,
                "pace_assessment": "Not Recorded",
                "camera_available": False,
                "voice_available": False,
            },
            "session_trends": {
                "strongest_answer": None,
                "weakest_answer": None,
                "performance_trend": "Insufficient Data",
                "star_adherence_pct": 0,
                "topic_breakdown": {},
            },
            "delivery_coaching": ["Complete interview answers using microphone and camera to receive personalized delivery coaching."],
        }

    # 1. Content Metric Collectors
    content_scores = []
    relevance_list = []
    accuracy_list = []
    depth_list = []
    completeness_list = []
    reasoning_list = []
    clarity_scores = []
    confidence_scores = []
    depth_levels_list = []
    all_technical_errors = []
    all_strengths = []
    all_weaknesses = []
    all_tradeoffs_demonstrated = []
    all_tradeoffs_missed = []
    star_scores_list = []
    topic_scores = {}
    answer_word_counts = []

    # 2. Delivery Signals Collectors
    wpm_list = []
    words_total = 0
    fillers_total = 0
    filler_rates = []
    pauses_total = 0
    face_presence_list = []
    looking_away_list = []
    posture_stability_list = []
    delivery_coaching_tips = []
    has_real_voice_telemetry = False
    has_real_cam_telemetry = False

    for idx, item in enumerate(answers):
        feedback = item.get("feedback") or {}
        answer_text = item.get("answer") or ""
        word_count = len(answer_text.strip().split())
        answer_word_counts.append(word_count)

        score = feedback.get("score")
        if score is not None:
            content_scores.append(float(score))

        c_score = feedback.get("clarity_score") or feedback.get("clarity")
        if c_score is not None:
            clarity_scores.append(float(c_score))

        conf_score = feedback.get("confidence_score") or feedback.get("confidence")
        if conf_score is not None:
            confidence_scores.append(float(conf_score))

        acc = feedback.get("technical_accuracy") or feedback.get("correctness") or feedback.get("technical_depth")
        if acc is not None:
            accuracy_list.append(float(acc))

        rel = feedback.get("relevance")
        if rel is not None:
            relevance_list.append(float(rel))

        dp = feedback.get("depth") or feedback.get("technical_depth")
        if dp is not None:
            depth_list.append(float(dp))

        comp = feedback.get("completeness")
        if comp is not None:
            completeness_list.append(float(comp))

        reas = feedback.get("reasoning")
        if reas is not None:
            reasoning_list.append(float(reas))

        d_level = feedback.get("technical_depth_level")
        if d_level is not None:
            depth_levels_list.append(int(d_level))

        errs = feedback.get("technical_errors")
        if isinstance(errs, list):
            all_technical_errors.extend(errs)

        star = feedback.get("star_analysis")
        if isinstance(star, dict) and "star_score" in star:
            star_scores_list.append(float(star["star_score"]))

        if isinstance(feedback.get("strengths"), list):
            all_strengths.extend(feedback["strengths"])
        if isinstance(feedback.get("improvements"), list):
            all_weaknesses.extend(feedback["improvements"])
        if isinstance(feedback.get("tradeoffs_identified"), list):
            all_tradeoffs_demonstrated.extend(feedback["tradeoffs_identified"])
        if isinstance(feedback.get("tradeoffs_missed"), list):
            all_tradeoffs_missed.extend(feedback["tradeoffs_missed"])

        # Topic Breakdown
        q_topic = item.get("topic") or "General"
        if q_topic not in topic_scores:
            topic_scores[q_topic] = []
        if score is not None:
            topic_scores[q_topic].append(float(score))

        # Extract Voice & Camera Signals if present
        signals = item.get("signals") or {}
        voice_sig = signals.get("voice") or {}
        cam_sig = signals.get("camera") or {}

        if voice_sig and isinstance(voice_sig, dict) and voice_sig.get("voice_available") is True and voice_sig.get("words_spoken", 0) > 0:
            has_real_voice_telemetry = True
            if "wpm" in voice_sig and voice_sig["wpm"] > 0:
                wpm_list.append(voice_sig["wpm"])
            words_total += int(voice_sig.get("words_spoken", word_count))
            fillers_total += int(voice_sig.get("filler_word_count", 0))
            if "filler_word_rate_pct" in voice_sig:
                filler_rates.append(float(voice_sig["filler_word_rate_pct"]))
            pauses_total += int(voice_sig.get("pause_count", 0))
            if isinstance(voice_sig.get("coaching_tips"), list):
                delivery_coaching_tips.extend(voice_sig["coaching_tips"])
        else:
            words_total += word_count

        if cam_sig and isinstance(cam_sig, dict) and cam_sig.get("camera_available") is True and cam_sig.get("total_frames_analyzed", 0) > 0:
            has_real_cam_telemetry = True
            if "face_presence_pct" in cam_sig:
                face_presence_list.append(float(cam_sig["face_presence_pct"]))
            if "looking_away_pct" in cam_sig:
                looking_away_list.append(float(cam_sig["looking_away_pct"]))
            if "posture_stability_score" in cam_sig:
                posture_stability_list.append(float(cam_sig["posture_stability_score"]))
            if isinstance(cam_sig.get("coaching_tips"), list):
                delivery_coaching_tips.extend(cam_sig["coaching_tips"])

    # 3. Content Calculations
    avg_content_score = round(sum(content_scores) / len(content_scores)) if content_scores else 70
    avg_clarity = round(sum(clarity_scores) / len(clarity_scores), 1) if clarity_scores else 7.0
    avg_confidence = round(sum(confidence_scores) / len(confidence_scores), 1) if confidence_scores else 7.0
    avg_technical = round(sum(accuracy_list) / len(accuracy_list), 1) if accuracy_list else (round(avg_content_score / 10.0, 1))
    avg_relevance = round(sum(relevance_list) / len(relevance_list), 1) if relevance_list else 7.5
    avg_depth = round(sum(depth_list) / len(depth_list), 1) if depth_list else 7.0
    avg_completeness = round(sum(completeness_list) / len(completeness_list), 1) if completeness_list else 7.0
    avg_reasoning = round(sum(reasoning_list) / len(reasoning_list), 1) if reasoning_list else 7.0
    avg_depth_level = round(sum(depth_levels_list) / len(depth_levels_list)) if depth_levels_list else 3

    # Deduplicate top strengths, weaknesses, technical errors, and trade-offs
    dedup_strengths = list(dict.fromkeys(all_strengths))[:4]
    dedup_weaknesses = list(dict.fromkeys(all_weaknesses))[:4]
    dedup_errors = list(dict.fromkeys(all_technical_errors))[:5]
    dedup_tradeoffs_dem = list(dict.fromkeys(all_tradeoffs_demonstrated))[:4]
    dedup_tradeoffs_miss = list(dict.fromkeys(all_tradeoffs_missed))[:4]

    why_explanations = {
        "technical_accuracy": "Consistently explained core mechanisms and architectural principles." if avg_technical >= 7.5 else "Foundational domain grasp; further precision on implementation trade-offs recommended.",
        "depth": f"Explanation depth averaged Level {avg_depth_level}/5 across responses.",
        "reasoning": "Clear logical progression with practical engineering trade-off awareness." if avg_reasoning >= 7.5 else "Consider explicitly evaluating edge-case failure modes and alternative designs.",
        "clarity": "Structured and articulate response delivery." if avg_clarity >= 7.5 else "Lead explanations with high-level summaries before diving into low-level details.",
    }

    # 4. Delivery Aggregations & Scoring
    avg_wpm = round(sum(wpm_list) / len(wpm_list)) if wpm_list else 135
    avg_filler_rate = round(sum(filler_rates) / len(filler_rates), 1) if filler_rates else (round((fillers_total / max(1, words_total)) * 100, 1) if words_total else 0.0)
    avg_face_pres = round(sum(face_presence_list) / len(face_presence_list)) if face_presence_list else 95
    avg_looking_away = round(sum(looking_away_list) / len(looking_away_list)) if looking_away_list else 10
    avg_posture = round(sum(posture_stability_list) / len(posture_stability_list)) if posture_stability_list else 90

    # Deterministic Delivery Score (0-100)
    pace_subscore = 100 if (110 <= avg_wpm <= 165) else (85 if (95 <= avg_wpm < 110 or 165 < avg_wpm <= 180) else 70)
    filler_subscore = 100 if (avg_filler_rate <= 2.0) else (85 if (avg_filler_rate <= 4.5) else (70 if avg_filler_rate <= 7.5 else 55))
    delivery_score = round(
        0.30 * pace_subscore +
        0.25 * filler_subscore +
        0.20 * min(100, max(0, avg_face_pres)) +
        0.15 * min(100, max(0, avg_posture)) +
        0.10 * min(100, max(0, 100 - avg_looking_away))
    )

    pace_assessment = "Optimal Conversational"
    if avg_wpm < 110: pace_assessment = "Deliberate / Slow"
    elif avg_wpm > 165: pace_assessment = "Fast / Brisk"

    dedup_delivery_coaching = list(dict.fromkeys(delivery_coaching_tips))[:5]
    if not dedup_delivery_coaching:
        dedup_delivery_coaching = [
            "Good vocal clarity and conversational pacing maintained throughout the interview.",
            "Consistent camera eye contact and stable framing observed.",
        ]

    # 5. Overall Weighted Score (85% Content, 15% Delivery)
    if has_real_voice_telemetry or has_real_cam_telemetry:
        overall_score = round(0.85 * avg_content_score + 0.15 * delivery_score)
    else:
        overall_score = avg_content_score

    # 6. Evaluation Reliability / Confidence (NOT psychological)
    avg_words = sum(answer_word_counts) / max(1, len(answer_word_counts))
    if avg_words >= 35 and (has_real_voice_telemetry or has_real_cam_telemetry):
        eval_reliability = "HIGH"
    elif avg_words >= 15:
        eval_reliability = "MEDIUM"
    else:
        eval_reliability = "LOW"

    # 7. Session-Level Trends
    strongest_idx = content_scores.index(max(content_scores)) if content_scores else 0
    weakest_idx = content_scores.index(min(content_scores)) if content_scores else 0
    strongest_q = answers[strongest_idx].get("question_text") if answers else None
    weakest_q = answers[weakest_idx].get("question_text") if answers else None

    trend_str = "Consistent Performance"
    if len(content_scores) >= 3:
        first_half = content_scores[:len(content_scores)//2]
        second_half = content_scores[len(content_scores)//2:]
        if (sum(second_half)/len(second_half)) - (sum(first_half)/len(first_half)) >= 5.0:
            trend_str = "Clear Improvement Over Interview Duration"
        elif (sum(first_half)/len(first_half)) - (sum(second_half)/len(second_half)) >= 5.0:
            trend_str = "Performance Decreased on Complex Later Questions"

    topic_summary = {k: round(sum(v)/len(v)) for k, v in topic_scores.items()} if topic_scores else {}
    star_adherence = round(sum(star_scores_list) / len(star_scores_list), 1) if star_scores_list else 0.0

    # 8. Validated Skills vs Skills Requiring Further Validation
    validated_skills_set = set()
    skills_requiring_val_set = set()
    for item in answers:
        fb = item.get("feedback") or {}
        val = fb.get("validated_skills") or []
        sc = fb.get("score", 70)
        q_skill = item.get("topic") or "Core Technical"
        if isinstance(val, list):
            for v in val:
                if sc >= 70:
                    validated_skills_set.add(str(v))
                else:
                    skills_requiring_val_set.add(str(v))
        if sc >= 75 and fb.get("technical_depth_level", 3) >= 3:
            validated_skills_set.add(q_skill)
        elif sc < 65 or len(fb.get("technical_errors", [])) > 0:
            skills_requiring_val_set.add(q_skill)

    # 9. Structured Competency Breakdown
    competency_breakdown = {
        "technical_fundamentals": round(avg_technical * 10),
        "architectural_depth": round(avg_depth * 10),
        "problem_solving_reasoning": round(avg_reasoning * 10),
        "behavioral_ownership": round(star_adherence) if star_scores_list else 80,
        "delivery_clarity": round(avg_clarity * 10),
    }

    # 10. Interview Readiness Level (Objective Assessment)
    if avg_content_score >= 85 and avg_depth_level >= 4:
        readiness_level = "Strong Technical Performance — Advanced Architectural Depth"
    elif avg_content_score >= 75:
        readiness_level = "Interview Ready for Target Role — Solid Conceptual Foundation"
    elif avg_content_score >= 60:
        readiness_level = "Developing — Recommended Additional Preparation on Core Systems"
    else:
        readiness_level = "Needs Significant Preparation on Core Technical Competencies"

    return {
        "overall_score": overall_score,
        "content_score": avg_content_score,
        "technical_score": avg_technical,
        "delivery_score": delivery_score,
        "clarity_score": avg_clarity,
        "confidence_score": avg_confidence,
        "evaluation_reliability": eval_reliability,
        "questions_total": total_questions,
        "questions_answered": answered_questions,
        "questions_skipped": skipped_questions,
        "completion_percentage": completion_rate,
        "top_strengths": dedup_strengths,
        "top_weaknesses": dedup_weaknesses,
        "top_tradeoffs_demonstrated": dedup_tradeoffs_dem,
        "top_tradeoffs_missed": dedup_tradeoffs_miss,
        "validated_skills": list(validated_skills_set)[:6],
        "skills_requiring_validation": list(skills_requiring_val_set)[:6],
        "competency_breakdown": competency_breakdown,
        "interview_readiness_level": readiness_level,
        "content_dimensions": {
            "relevance": avg_relevance,
            "technical_accuracy": avg_technical,
            "depth": avg_depth,
            "completeness": avg_completeness,
            "reasoning": avg_reasoning,
            "clarity": avg_clarity,
            "avg_depth_level": avg_depth_level,
            "all_technical_errors": dedup_errors,
            "why_explanations": why_explanations,
        },
        "delivery_metrics": {
            "avg_wpm": avg_wpm,
            "total_words_spoken": words_total,
            "total_filler_words": fillers_total,
            "avg_filler_rate_pct": avg_filler_rate,
            "total_pauses": pauses_total,
            "avg_face_presence_pct": avg_face_pres,
            "avg_looking_away_pct": avg_looking_away,
            "avg_posture_stability": avg_posture,
            "pace_assessment": pace_assessment,
            "camera_available": has_real_cam_telemetry,
            "voice_available": has_real_voice_telemetry,
        },
        "session_trends": {
            "strongest_question": strongest_q,
            "weakest_question": weakest_q,
            "performance_trend": trend_str,
            "star_adherence_pct": star_adherence,
            "topic_breakdown": topic_summary,
        },
        "delivery_coaching": dedup_delivery_coaching,
    }


def generate_interview_strategy(
    role: str,
    experience: str,
    focus: str,
    difficulty: str,
    resume_ctx: str = "",
    question_count: int = 5,
) -> Dict[str, Any]:
    """
    Builds a deterministic, role-tailored interview strategy mapping competency stages across N questions.
    Works with arbitrary roles and incorporates candidate resume skills where available.
    """
    diff_map = {"easy": 2, "medium": 3, "hard": 4}
    base_diff = diff_map.get(str(difficulty).lower().strip(), 3)

    claimed_skills = []
    if resume_ctx:
        keywords = ["react", "node", "python", "fastapi", "django", "flask", "postgresql", "sql", "redis",
                    "docker", "kubernetes", "aws", "gcp", "kafka", "graphql", "typescript", "microservices",
                    "system design", "distributed systems", "ci/cd", "rest api"]
        ctx_lower = resume_ctx.lower()
        for kw in keywords:
            if kw in ctx_lower:
                claimed_skills.append(kw.title())

    if not claimed_skills:
        claimed_skills = [focus or "Core Engineering", "System Architecture", "Problem Solving"]

    # Stage distribution archetype
    stages = []
    for i in range(question_count):
        if i == 0:
            stages.append("fundamentals")
        elif i == question_count - 1:
            stages.append("behavioral")
        elif i == 1:
            stages.append("applied")
        elif i == 2:
            stages.append("deep_technical")
        else:
            stages.append("system_design" if i % 2 == 1 else "deep_technical")

    return {
        "role": role,
        "experience": experience,
        "focus": focus,
        "base_difficulty": base_diff,
        "total_questions": question_count,
        "stages": stages,
        "claimed_skills": claimed_skills,
        "skills_to_validate": list(claimed_skills),
        "validated_skills": [],
        "competencies": [
            {"name": "Fundamentals & Mechanics", "weight": 0.25},
            {"name": "Applied Implementation", "weight": 0.30},
            {"name": "Trade-offs & Concurrency", "weight": 0.25},
            {"name": "Communication & STAR Ownership", "weight": 0.20},
        ],
    }


# =====================================================================
# 3. INTERVIEW ORCHESTRATION WITH POSTGRESQL ROW LOCKING
# =====================================================================

class InterviewOrchestrator:

    @staticmethod
    def initiate_interview(
        user_id: str,
        role: str,
        experience: str,
        focus: str,
        difficulty: str,
        resume_ctx: str = "",
        question_count: int = 5,
        job_description: str = "",
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Creates an interview session with structured strategy and initial questions.
        Stores strategy, interview_state, job_description, and initial question set in Neon PostgreSQL.
        """
        candidate_profile = {}
        if user_id:
            user_rec = get_user_by_id(user_id) or {}
            candidate_profile = {
                "education": user_rec.get("education", ""),
                "current_job": user_rec.get("current_job", ""),
                "target_job": user_rec.get("target_job", ""),
                "bio": user_rec.get("bio", ""),
            }
            if not resume_ctx and user_rec.get("resume_text"):
                resume_ctx = user_rec.get("resume_text", "")

        strategy = generate_interview_strategy(
            role=role,
            experience=experience,
            focus=focus,
            difficulty=difficulty,
            resume_ctx=resume_ctx,
            question_count=question_count,
        )

        initial_state = {
            "role": role,
            "experience": experience,
            "focus": focus,
            "target_difficulty": strategy["base_difficulty"],
            "current_difficulty": strategy["base_difficulty"],
            "current_question_index": 0,
            "questions_asked": 1,
            "questions_answered": 0,
            "total_questions": question_count,
            "technical_strengths": [],
            "technical_gaps": [],
            "topics_covered": [],
            "topics_weak": [],
            "behavioral_strengths": [],
            "behavioral_gaps": [],
            "validated_skills": [],
            "skills_to_validate": strategy["skills_to_validate"],
            "recent_answer_quality": 0,
            "recent_depth_level": 0,
            "recent_recommended_action": "continue",
            "question_types_used": ["technical"],
            "skills_tested": [],
            "interview_progress": 0.0,
        }

        prompt = build_question_generation_prompt(
            role=role,
            experience=experience,
            focus=focus,
            difficulty=difficulty,
            resume_ctx=resume_ctx,
            count=question_count,
            candidate_profile=candidate_profile,
            job_description=job_description,
        )

        try:
            ai_res = gemini_service.execute_structured_request(
                prompt=prompt,
                request_type="QUESTION_GENERATION",
                validator=lambda data: validate_questions_output(data, expected_count=question_count),
                complexity=difficulty,
            )
            questions = ai_res.data
        except Exception as e:
            logger.error(f"Question generation failed: {e}. Using deterministic technical question fallback.")
            role_l = role.lower()
            if "frontend" in role_l or "ui" in role_l:
                questions = [
                    {
                        "id": 1,
                        "question": f"In a modern frontend application using {focus}, how does the browser rendering pipeline interact with virtual DOM reconciliation and state management?",
                        "topic": "Frontend Core",
                        "skill": focus,
                        "difficulty": strategy["base_difficulty"],
                        "question_type": "technical",
                        "intent": "test_fundamentals",
                        "expected_concepts": ["Virtual DOM", "Reconciliation", "Rendering Lifecycle", "State Hydration"],
                        "stage": "fundamentals",
                    },
                    {
                        "id": 2,
                        "question": f"Describe a scenario where you diagnosed and fixed client-side performance degradation or memory leaks in {focus}.",
                        "topic": "Frontend Performance",
                        "skill": "Performance Optimization",
                        "difficulty": strategy["base_difficulty"],
                        "question_type": "technical",
                        "intent": "applied_scenario",
                        "expected_concepts": ["Bundle Size", "Profiling", "Memoization", "Layout Thrashing"],
                        "stage": "applied",
                    },
                    {
                        "id": 3,
                        "question": "How do you architect a resilient frontend design system with micro-frontends, caching, and accessibility guarantees?",
                        "topic": "Frontend Architecture",
                        "skill": "Design Systems",
                        "difficulty": min(5, strategy["base_difficulty"] + 1),
                        "question_type": "system_design",
                        "intent": "system_design",
                        "expected_concepts": ["Component Modularity", "Caching", "Accessibility", "State Hydration"],
                        "stage": "deep_technical",
                    },
                ]
            elif "backend" in role_l:
                questions = [
                    {
                        "id": 1,
                        "question": f"Can you explain database indexing mechanics (such as B-Tree vs Hash indexing) and how write amplification impacts high-throughput APIs in {focus}?",
                        "topic": "Database Fundamentals",
                        "skill": focus,
                        "difficulty": strategy["base_difficulty"],
                        "question_type": "technical",
                        "intent": "test_fundamentals",
                        "expected_concepts": ["B-Tree Indexing", "Write Amplification", "WAL Logging", "Query Plans"],
                        "stage": "fundamentals",
                    },
                    {
                        "id": 2,
                        "question": "How do you implement distributed cache invalidation (e.g. Cache-Aside vs Write-Through) while preventing cache stampedes under sudden traffic spikes?",
                        "topic": "Distributed Caching",
                        "skill": "Caching Strategies",
                        "difficulty": strategy["base_difficulty"],
                        "question_type": "technical",
                        "intent": "applied_scenario",
                        "expected_concepts": ["Cache Invalidation", "Thundering Herd", "Pub/Sub Bus", "TTL Strategies"],
                        "stage": "applied",
                    },
                    {
                        "id": 3,
                        "question": "How would you design an idempotent, horizontally scalable payment processing API with transactional outbox and distributed locking?",
                        "topic": "Backend System Design",
                        "skill": "Distributed Architecture",
                        "difficulty": min(5, strategy["base_difficulty"] + 1),
                        "question_type": "system_design",
                        "intent": "system_design",
                        "expected_concepts": ["Idempotency Keys", "Transactional Outbox", "Distributed Locks", "Dead Letter Queues"],
                        "stage": "deep_technical",
                    },
                ]
            elif "ml" in role_l or "machine learning" in role_l or "ai" in role_l:
                questions = [
                    {
                        "id": 1,
                        "question": f"In machine learning systems, how do you handle data drift, covariate shift, and evaluate embeddings for semantic retrieval in {focus}?",
                        "topic": "ML Fundamentals",
                        "skill": focus,
                        "difficulty": strategy["base_difficulty"],
                        "question_type": "technical",
                        "intent": "test_fundamentals",
                        "expected_concepts": ["Data Drift", "Covariate Shift", "Embedding Evaluation", "Precision/Recall"],
                        "stage": "fundamentals",
                    },
                    {
                        "id": 2,
                        "question": "Describe your approach to optimizing LLM inference latency through quantization (e.g. INT8/FP4), KV caching, and batching strategies.",
                        "topic": "LLM Inference Systems",
                        "skill": "Model Optimization",
                        "difficulty": strategy["base_difficulty"],
                        "question_type": "technical",
                        "intent": "test_tradeoff_reasoning",
                        "expected_concepts": ["Quantization", "KV Cache", "Paged Attention", "Latency vs Perplexity"],
                        "stage": "applied",
                    },
                    {
                        "id": 3,
                        "question": "How do you design a production-grade RAG pipeline capable of handling 50k QPS with hybrid vector/BM25 search and real-time reranking?",
                        "topic": "AI System Design",
                        "skill": "RAG Architecture",
                        "difficulty": min(5, strategy["base_difficulty"] + 1),
                        "question_type": "system_design",
                        "intent": "system_design",
                        "expected_concepts": ["Vector Indexing (HNSW)", "Hybrid Search", "Cross-Encoder Reranking", "Caching"],
                        "stage": "deep_technical",
                    },
                ]
            elif "devops" in role_l or "sre" in role_l or "cloud" in role_l:
                questions = [
                    {
                        "id": 1,
                        "question": f"In a cloud-native infrastructure using {focus}, how do you diagnose pod CrashLoopBackOff states, split-brain scenarios, and manage etcd consistency?",
                        "topic": "Cloud Infrastructure",
                        "skill": focus,
                        "difficulty": strategy["base_difficulty"],
                        "question_type": "technical",
                        "intent": "test_fundamentals",
                        "expected_concepts": ["etcd Raft Consensus", "CrashLoop Triage", "Liveness/Readiness Probes", "Resource Limits"],
                        "stage": "fundamentals",
                    },
                    {
                        "id": 2,
                        "question": "How do you implement zero-downtime blue/green or canary deployments across multi-region Kubernetes clusters with automated rollbacks?",
                        "topic": "Deployment Automation",
                        "skill": "CI/CD & SRE",
                        "difficulty": strategy["base_difficulty"],
                        "question_type": "technical",
                        "intent": "applied_scenario",
                        "expected_concepts": ["Canary Traffic Shifting", "Automated Rollback", "Service Meshes", "Health Probes"],
                        "stage": "applied",
                    },
                    {
                        "id": 3,
                        "question": "How would you design a disaster recovery and chaos engineering strategy for a multi-region infrastructure requiring 99.99% uptime?",
                        "topic": "SRE Architecture",
                        "skill": "Reliability & DR",
                        "difficulty": min(5, strategy["base_difficulty"] + 1),
                        "question_type": "system_design",
                        "intent": "system_design",
                        "expected_concepts": ["RTO/RPO SLA", "Chaos Injection", "Multi-region DNS Failover", "Circuit Breakers"],
                        "stage": "deep_technical",
                    },
                ]
            else:
                questions = [
                    {
                        "id": 1,
                        "question": f"Can you explain the core architectural principles and internal mechanics of {focus} in a {role} role?",
                        "topic": focus,
                        "skill": focus,
                        "difficulty": strategy["base_difficulty"],
                        "question_type": "technical",
                        "intent": "test_fundamentals",
                        "expected_concepts": ["Architecture", "Tradeoffs", "Best Practices"],
                        "stage": "fundamentals",
                    },
                    {
                        "id": 2,
                        "question": f"Describe an applied engineering challenge you solved in {focus} and how you evaluated implementation trade-offs.",
                        "topic": focus,
                        "skill": "Applied Implementation",
                        "difficulty": strategy["base_difficulty"],
                        "question_type": "technical",
                        "intent": "applied_scenario",
                        "expected_concepts": ["Problem Solving", "Scalability", "Resolution"],
                        "stage": "applied",
                    },
                    {
                        "id": 3,
                        "question": f"How do you design for high concurrency, failure modes, and performance optimization in {role} systems?",
                        "topic": "System Architecture",
                        "skill": "Concurrency & Scale",
                        "difficulty": min(5, strategy["base_difficulty"] + 1),
                        "question_type": "system_design",
                        "intent": "system_design",
                        "expected_concepts": ["Concurrency", "Failure Isolation", "Latency"],
                        "stage": "deep_technical",
                    },
                ]
            ai_res = None

        with get_db() as conn:
            with dict_cursor(conn) as cur:
                cur.execute(
                    """
                    INSERT INTO interviews (
                        user_id, role, experience, focus, difficulty, status, questions, answers,
                        interview_state, strategy, resume_context, job_description
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, '[]'::jsonb, %s, %s, %s, %s)
                    RETURNING id, role, experience, focus, difficulty, status, questions, interview_state, strategy, created_at
                    """,
                    (
                        user_id,
                        role,
                        experience,
                        focus,
                        difficulty,
                        "active",
                        json.dumps(questions),
                        json.dumps(initial_state),
                        json.dumps(strategy),
                        resume_ctx or "",
                        job_description or "",
                    )
                )
                row = cur.fetchone()

        session_id = str(row["id"])
        if ai_res:
            record_ai_usage("QUESTION_GENERATION", result=ai_res, interview_id=session_id, user_id=user_id)
        else:
            record_ai_usage("QUESTION_GENERATION", interview_id=session_id, user_id=user_id, status="fallback", model="fallback/heuristic")

        session_dict = dict(row)
        session_dict["id"] = session_id
        session_dict["questions"] = questions
        session_dict["interview_state"] = initial_state
        session_dict["strategy"] = strategy
        if hasattr(session_dict.get("created_at"), "isoformat"):
            session_dict["created_at"] = session_dict["created_at"].isoformat()

        return session_dict, questions

    @staticmethod
    def evaluate_and_submit_answer(
        session_id: str,
        user_id: str,
        question_data: Dict[str, Any],
        answer_text: str,
        signals: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Evaluates a candidate's answer with:
        1. PostgreSQL Row Locking (SELECT FOR UPDATE): Concurrency safety across replicas.
        2. Duplicate Prevention / Idempotency: Returns cached evaluation without Gemini call.
        3. MCQ Deterministic Processing: 0 AI calls for objective questions.
        4. Isolated Subjective Prompt: Compact evaluation without historical overhead.
        5. Delivery Signals Persistence: Stores voice/camera telemetry for coaching analysis.
        6. Dynamic Interview State Update: Updates strengths, gaps, validated skills, and difficulty.
        """
        if isinstance(question_data, str):
            question_data = {"question": question_data, "id": str(question_data)}
        elif not isinstance(question_data, dict):
            question_data = {"question": str(question_data), "id": str(question_data)}

        target_qid = question_data.get("id")
        q_type = str(question_data.get("question_type", "technical")).lower()
        correct_answer = question_data.get("correct_answer")

        # ── TRANSACTION WITH ROW LOCKING ──────────────────────────────
        with get_db() as conn:
            with dict_cursor(conn) as cur:
                cur.execute(
                    """
                    SELECT questions, answers, role, difficulty, interview_state, strategy
                    FROM interviews
                    WHERE id = %s AND user_id = %s
                    FOR UPDATE
                    """,
                    (session_id, user_id)
                )
                row = cur.fetchone()

                if not row:
                    raise ValueError("Session not found or unauthorized")

                current_answers = row.get("answers") or []
                if isinstance(current_answers, str):
                    current_answers = json.loads(current_answers)

                state = row.get("interview_state") or {}
                if isinstance(state, str):
                    state = json.loads(state)

                strategy = row.get("strategy") or {}
                if isinstance(strategy, str):
                    strategy = json.loads(strategy)

                # ── IDEMPOTENCY CHECK (Inside Lock) ───────────────────
                for existing in current_answers:
                    if existing.get("question_id") == target_qid:
                        logger.info(f"Duplicate submission detected for session {session_id}, question {target_qid}. Returning cached evaluation.")
                        record_ai_usage(
                            "ANSWER_EVALUATION",
                            interview_id=session_id,
                            user_id=user_id,
                            status="cached",
                            cache_hit=True,
                            model="cache",
                            conn=conn,
                        )
                        return existing.get("feedback", {})

                # ── MCQ / OBJECTIVE QUESTION DETERMINISTIC CHECK ──────
                if q_type == "mcq" and correct_answer is not None:
                    is_correct = str(answer_text).strip().lower() == str(correct_answer).strip().lower()
                    score = 100 if is_correct else 0
                    feedback = {
                        "score": score,
                        "score_10": 10 if is_correct else 0,
                        "relevance": 10 if is_correct else 2,
                        "technical_accuracy": 10 if is_correct else 0,
                        "correctness": 10 if is_correct else 0,
                        "depth": 10 if is_correct else 2,
                        "technical_depth": 10 if is_correct else 2,
                        "completeness": 10 if is_correct else 0,
                        "reasoning": 10 if is_correct else 5,
                        "clarity_score": 10 if is_correct else 5,
                        "confidence_score": 10 if is_correct else 5,
                        "technical_depth_level": 5 if is_correct else 1,
                        "technical_errors": [] if is_correct else ["Incorrect option selected"],
                        "missing_concepts": [],
                        "validated_skills": [question_data.get("topic", "MCQ Recall")] if is_correct else [],
                        "star_analysis": {"situation": True, "task": True, "action": True, "result": True, "star_score": 100},
                        "recommended_next_action": "increase_difficulty" if is_correct else "probe_deeper",
                        "recommended_follow_up": "",
                        "feedback": "Correct answer selected." if is_correct else f"Incorrect. Correct answer is: {correct_answer}",
                        "strengths": ["Accurate knowledge recall"] if is_correct else [],
                        "improvements": [] if is_correct else [f"Review {question_data.get('topic', 'concept')} fundamentals"],
                    }
                    ai_res = None
                else:
                    # ── ISOLATED SUBJECTIVE AI EVALUATION ───────────────
                    prompt = build_answer_evaluation_prompt(
                        question_text=question_data.get("question", ""),
                        answer_text=answer_text,
                        expected_concepts=question_data.get("expected_concepts", []),
                        question_type=q_type,
                        role=row.get("role", "Software Engineer"),
                        difficulty=row.get("difficulty", "Medium"),
                        topic=question_data.get("topic", "General"),
                    )

                    try:
                        ai_res = gemini_service.execute_structured_request(
                            prompt=prompt,
                            request_type="ANSWER_EVALUATION",
                            validator=validate_answer_evaluation,
                            complexity=row.get("difficulty", "Medium"),
                        )
                        feedback = ai_res.data
                    except Exception as e:
                        logger.error(f"Answer evaluation AI error: {e}. Applying safe fallback evaluation.")
                        words = len(answer_text.strip().split())
                        # Check for dense technical domain vocabulary (substance over length)
                        tech_keywords = [
                            "partition", "commit log", "syscall", "throughput", "concurrency",
                            "latency", "sharding", "replication", "cache", "offset", "append-only",
                            "sendfile", "index", "btree", "tradeoff", "consensus", "wal", "lock"
                        ]
                        tech_density = sum(1 for kw in tech_keywords if kw in answer_text.lower())

                        if words < 10 and tech_density == 0:
                            fb_score = 48
                            fb_depth = 1
                            fb_acc = 5
                            fb_strengths = ["Brief response submitted"]
                            fb_improvements = ["Elaborate on core engineering mechanics and provide architectural detail"]
                            fb_action = "probe_deeper"
                        elif tech_density >= 2 or words >= 25:
                            fb_score = 85
                            fb_depth = 4
                            fb_acc = 8
                            fb_strengths = ["Comprehensive conceptual articulation", "Good technical reasoning"]
                            fb_improvements = ["Consider quantifying performance trade-offs"]
                            fb_action = "increase_difficulty"
                        else:
                            fb_score = 65
                            fb_depth = 2
                            fb_acc = 6
                            fb_strengths = ["Clear high-level overview"]
                            fb_improvements = ["Add practical examples and discuss failure edge cases"]
                            fb_action = "continue"

                        star_score = 100 if any(k in answer_text.lower() for k in ("situation", "task", "action", "result")) else 75

                        feedback = {
                            "score": fb_score,
                            "score_10": round(fb_score / 10),
                            "relevance": 8,
                            "technical_accuracy": fb_acc,
                            "correctness": fb_acc,
                            "depth": fb_depth * 2,
                            "technical_depth": fb_depth * 2,
                            "completeness": round(fb_score / 10),
                            "reasoning": 7,
                            "clarity_score": 8,
                            "confidence_score": 7,
                            "evidence": 7,
                            "technical_depth_level": fb_depth,
                            "technical_errors": ["Superficial explanation"] if words < 12 else [],
                            "missing_concepts": ["System mechanics", "Trade-offs"] if words < 12 else [],
                            "tradeoffs_identified": ["Latency vs consistency", "Concurrency models"] if tech_density >= 2 else [],
                            "tradeoffs_missed": ["Failure isolation and recovery"] if tech_density < 2 else [],
                            "evidence_summary": f"Demonstrated Level {fb_depth}/5 understanding with {'solid architectural reasoning' if fb_score >= 75 else 'basic high-level overview'}.",
                            "validated_skills": [question_data.get("topic", "General Engineering")] if fb_score >= 75 else [],
                            "star_analysis": {
                                "situation": True,
                                "task": True,
                                "action": True,
                                "result": True if star_score == 100 else False,
                                "star_score": star_score,
                            },
                            "recommended_next_action": fb_action,
                            "recommended_follow_up": "Probe on failure recovery" if words < 12 else "",
                            "feedback": f"Answer recorded. {'Detailed technical response.' if fb_score >= 75 else 'Brief response; further depth recommended.'}",
                            "strengths": fb_strengths,
                            "improvements": fb_improvements,
                            "evaluation_status": "fallback",
                        }
                        ai_res = None

                # ── UPDATE INTERVIEW STATE DETERMINISTICALLY ──────────
                eval_score = feedback.get("score", 70)
                eval_depth = feedback.get("technical_depth_level", 3)
                q_topic = question_data.get("topic", "General")
                q_skill = question_data.get("skill") or q_topic

                state.setdefault("topics_covered", [])
                if q_topic not in state["topics_covered"]:
                    state["topics_covered"].append(q_topic)

                state.setdefault("skills_tested", [])
                if q_skill not in state["skills_tested"]:
                    state["skills_tested"].append(q_skill)

                state.setdefault("technical_strengths", [])
                state.setdefault("technical_gaps", [])
                state.setdefault("validated_skills", [])
                state.setdefault("skills_to_validate", strategy.get("skills_to_validate", []))

                if eval_score >= 75 and eval_depth >= 3:
                    for s in feedback.get("strengths", []):
                        if s not in state["technical_strengths"]:
                            state["technical_strengths"].append(s)
                    for val_s in feedback.get("validated_skills", []):
                        if val_s not in state["validated_skills"]:
                            state["validated_skills"].append(val_s)
                    if q_skill not in state["validated_skills"]:
                        state["validated_skills"].append(q_skill)
                    
                    # Remove from unvalidated queue if present
                    state["skills_to_validate"] = [
                        s for s in state["skills_to_validate"]
                        if s.lower() != q_skill.lower() and s.lower() != q_topic.lower()
                    ]
                elif eval_score < 65:
                    for w in feedback.get("improvements", []):
                        if w not in state["technical_gaps"]:
                            state["technical_gaps"].append(w)
                    if q_topic not in state["topics_weak"]:
                        state["topics_weak"].append(q_topic)

                # Controlled Difficulty Progression
                curr_diff = state.get("current_difficulty", 3)
                if eval_score >= 85 and eval_depth >= 4:
                    new_diff = min(5, curr_diff + 1)
                elif eval_score < 60:
                    new_diff = max(1, curr_diff - 1)
                else:
                    new_diff = curr_diff
                state["current_difficulty"] = new_diff

                state["recent_answer_quality"] = eval_score
                state["recent_depth_level"] = eval_depth
                state["recent_recommended_action"] = feedback.get("recommended_next_action", "continue")
                state["questions_answered"] = len(current_answers) + 1
                total_target = state.get("total_questions", 5)
                state["interview_progress"] = round(min(1.0, state["questions_answered"] / max(1, total_target)), 2)

                # ── PERSIST IN NEON ───────────────────────────────────
                current_answers.append({
                    "question_id": target_qid,
                    "question_text": question_data.get("question", ""),
                    "topic": q_topic,
                    "skill": q_skill,
                    "question_type": q_type,
                    "answer": answer_text,
                    "feedback": feedback,
                    "signals": signals or {},
                    "submitted_at": datetime.now(timezone.utc).isoformat(),
                })

                cur.execute(
                    """
                    UPDATE interviews
                    SET answers = %s,
                        interview_state = %s
                    WHERE id = %s AND user_id = %s
                    """,
                    (json.dumps(current_answers), json.dumps(state), session_id, user_id)
                )

        if ai_res:
            record_ai_usage("ANSWER_EVALUATION", result=ai_res, interview_id=session_id, user_id=user_id)
        elif q_type != "mcq":
            record_ai_usage("ANSWER_EVALUATION", interview_id=session_id, user_id=user_id, status="fallback", model="fallback/heuristic")

        return feedback

    @staticmethod
    def get_or_generate_next_question(
        session_id: str,
        user_id: str,
        current_index: int,
    ) -> Dict[str, Any]:
        """
        Dynamically retrieves or adaptively generates the next interview question.
        Reacts to the previous answer quality, demonstrated depth, and interview strategy stage.
        """
        with get_db() as conn:
            with dict_cursor(conn) as cur:
                cur.execute(
                    """
                    SELECT id, role, experience, focus, difficulty, questions, answers,
                           interview_state, strategy, resume_context, job_description
                    FROM interviews
                    WHERE id = %s AND user_id = %s
                    FOR UPDATE
                    """,
                    (session_id, user_id)
                )
                row = cur.fetchone()

                if not row:
                    raise ValueError("Session not found or unauthorized")

                questions = row.get("questions") or []
                if isinstance(questions, str):
                    questions = json.loads(questions)

                answers = row.get("answers") or []
                if isinstance(answers, str):
                    answers = json.loads(answers)

                state = row.get("interview_state") or {}
                if isinstance(state, str):
                    state = json.loads(state)

                strategy = row.get("strategy") or {}
                if isinstance(strategy, str):
                    strategy = json.loads(strategy)

                total_questions = strategy.get("total_questions", len(questions) or 5)
                next_index = current_index + 1

                # If interview target is reached
                if next_index >= total_questions and len(answers) >= total_questions:
                    return {"done": True, "message": "Interview complete", "session_id": session_id}

                # If next question is already available in the pre-generated questions list
                if next_index < len(questions):
                    return {"question": questions[next_index], "index": next_index, "done": False}

                # ── DYNAMIC ADAPTIVE QUESTION GENERATION ───────────────
                stages = strategy.get("stages", ["fundamentals", "applied", "deep_technical", "system_design", "behavioral"])
                stage_target = stages[min(next_index, len(stages) - 1)]

                prev_q = questions[current_index] if current_index < len(questions) else (questions[-1] if questions else {})
                prev_ans = answers[-1].get("answer", "") if answers else ""
                prev_eval = answers[-1].get("feedback", {}) if answers else {}

                topics_covered = state.get("topics_covered", [])
                target_diff = state.get("current_difficulty", strategy.get("base_difficulty", 3))
                rec_action = state.get("recent_recommended_action", "continue")

                # Anti-looping guard: limit repeated probing of the same topic to max 2 probes
                topic_probes = state.get("topic_probe_counts", {})
                prev_topic_key = prev_q.get("topic", "General")
                current_probes = topic_probes.get(prev_topic_key, 0)
                if rec_action == "probe_deeper":
                    if current_probes >= 2:
                        rec_action = "continue"
                        if prev_topic_key not in state.get("technical_gaps", []):
                            state.setdefault("technical_gaps", []).append(prev_topic_key)
                    else:
                        topic_probes[prev_topic_key] = current_probes + 1
                state["topic_probe_counts"] = topic_probes

                candidate_profile = {}
                if user_id:
                    user_rec = get_user_by_id(user_id) or {}
                    candidate_profile = {
                        "education": user_rec.get("education", ""),
                        "current_job": user_rec.get("current_job", ""),
                        "target_job": user_rec.get("target_job", ""),
                        "bio": user_rec.get("bio", ""),
                    }

                prompt = build_adaptive_next_question_prompt(
                    role=row.get("role", "Software Engineer"),
                    experience=row.get("experience", "Mid-Level"),
                    current_index=next_index,
                    total_questions=total_questions,
                    stage_target=stage_target,
                    target_difficulty=target_diff,
                    previous_question=prev_q,
                    previous_answer=prev_ans,
                    previous_eval=prev_eval,
                    topics_covered=topics_covered,
                    recommended_action=rec_action,
                    resume_ctx=row.get("resume_context", ""),
                    skills_to_validate=state.get("skills_to_validate", []),
                    validated_skills=state.get("validated_skills", []),
                    technical_gaps=state.get("technical_gaps", []),
                    technical_strengths=state.get("technical_strengths", []),
                    candidate_profile=candidate_profile,
                    job_description=row.get("job_description", ""),
                )

                try:
                    ai_res = gemini_service.execute_structured_request(
                        prompt=prompt,
                        request_type="ADAPTIVE_QUESTION",
                        validator=validate_adaptive_question,
                        complexity=row.get("difficulty", "Medium"),
                    )
                    next_question = ai_res.data
                except Exception as e:
                    logger.error(f"Adaptive question generation failed: {e}. Using deterministic stage question.")
                    fallback_intent = "probe_technical_gap" if rec_action == "probe_deeper" else ("validate_resume_skill" if state.get("skills_to_validate") else "system_design" if stage_target == "system_design" else ("behavioral" if stage_target == "behavioral" else "test_tradeoff_reasoning"))
                    next_question = {
                        "id": next_index + 1,
                        "question": f"In a {row.get('role', 'Technical')} role, how do you handle {stage_target.replace('_', ' ')} challenges and edge-cases?",
                        "topic": f"{stage_target.title()} Scenario",
                        "skill": row.get("focus", "Engineering"),
                        "difficulty": target_diff,
                        "question_type": "behavioral" if stage_target == "behavioral" else "technical",
                        "intent": fallback_intent,
                        "expected_concepts": ["Problem Solving", "Architecture", "Trade-offs"],
                        "follow_up_allowed": True,
                        "stage": stage_target,
                    }
                    ai_res = None

                if next_index < len(questions):
                    questions[next_index] = next_question
                else:
                    questions.append(next_question)

                state["current_question_index"] = next_index
                state["questions_asked"] = len(questions)

                cur.execute(
                    """
                    UPDATE interviews
                    SET questions = %s,
                        interview_state = %s
                    WHERE id = %s AND user_id = %s
                    """,
                    (json.dumps(questions), json.dumps(state), session_id, user_id)
                )

        if ai_res:
            record_ai_usage("ADAPTIVE_QUESTION", result=ai_res, interview_id=session_id, user_id=user_id)

        return {"question": next_question, "index": next_index, "done": False}

    @staticmethod
    def get_or_generate_final_report(session_id: str, user_id: str) -> Dict[str, Any]:
        """
        Generates or retrieves the final comprehensive interview report.
        1. If report already exists in Neon -> returns stored report (0 AI calls).
        2. Calculates deterministic scores first.
        3. Sends compact summary to Gemini for narrative evaluation only.
        4. Persists the generated report.
        """
        with get_db() as conn:
            with dict_cursor(conn) as cur:
                cur.execute(
                    """
                    SELECT id, role, experience, focus, difficulty, status, questions, answers,
                           report, overall_score, category_scores, interview_state, created_at
                    FROM interviews
                    WHERE id = %s AND user_id = %s
                    FOR UPDATE
                    """,
                    (session_id, user_id)
                )
                row = cur.fetchone()

                if not row:
                    raise ValueError("Session not found or unauthorized")

                # ── RETURN STORED REPORT (Idempotency) ─────────────────
                existing_report = row.get("report")
                if existing_report:
                    record_ai_usage(
                        "FINAL_REPORT",
                        interview_id=session_id,
                        user_id=user_id,
                        status="cached",
                        cache_hit=True,
                        model="cache",
                        conn=conn,
                    )
                    if isinstance(existing_report, str):
                        return json.loads(existing_report)
                    return existing_report

                questions = row.get("questions") or []
                if isinstance(questions, str):
                    questions = json.loads(questions)

                answers = row.get("answers") or []
                if isinstance(answers, str):
                    answers = json.loads(answers)

                # ── BACKEND DETERMINISTIC SCORING ──────────────────────
                scores = calculate_interview_scores(questions, answers)

                # ── COMPACT NARRATIVE REPORT REQUEST ───────────────────
                prompt = build_final_report_prompt(
                    compact_summary=scores,
                    role=row.get("role", "Software Engineer"),
                    experience=row.get("experience", "Mid-Level"),
                )

                try:
                    ai_res = gemini_service.execute_structured_request(
                        prompt=prompt,
                        request_type="FINAL_REPORT",
                        validator=validate_final_report,
                        complexity=row.get("difficulty", "Medium"),
                    )
                    narrative = ai_res.data
                except Exception as e:
                    logger.error(f"Final report AI narrative error: {e}. Using deterministic narrative fallback.")
                    narrative = {
                        "summary": f"Candidate completed the {row.get('role', 'Technical')} interview demonstrating solid problem solving.",
                        "key_strengths": scores["top_strengths"] or ["Good conceptual foundation"],
                        "growth_areas": scores["top_weaknesses"] or ["Continue practicing high-complexity scenarios"],
                        "validated_skills": scores.get("validated_skills") or ["Core Fundamentals"],
                        "skills_requiring_validation": scores.get("skills_requiring_validation") or ["Advanced Scale"],
                        "technical_topics_to_revise": ["Core architecture trade-offs"],
                        "communication_recommendations": ["Structure answers with clear problem-solution-impact flow"],
                        "interview_readiness_level": scores.get("interview_readiness_level") or "Ready for Mid-Level Roles",
                        "hiring_recommendation": "Recommended for Next Technical Round" if scores["overall_score"] >= 70 else "Needs Additional Preparation",
                    }
                    ai_res = None

                # ── COMBINE DETERMINISTIC METRICS + AI NARRATIVE ───────
                full_report = {
                    "overall_score": scores["overall_score"],
                    "content_score": scores["content_score"],
                    "technical_score": scores["technical_score"],
                    "delivery_score": scores["delivery_score"],
                    "clarity_score": scores["clarity_score"],
                    "confidence_score": scores["confidence_score"],
                    "evaluation_reliability": scores["evaluation_reliability"],
                    "questions_total": scores["questions_total"],
                    "questions_answered": scores["questions_answered"],
                    "questions_skipped": scores["questions_skipped"],
                    "completion_percentage": scores["completion_percentage"],
                    "summary": narrative["summary"],
                    "key_strengths": narrative["key_strengths"],
                    "growth_areas": narrative["growth_areas"],
                    "validated_skills": narrative.get("validated_skills") or scores.get("validated_skills", []),
                    "skills_requiring_validation": narrative.get("skills_requiring_validation") or scores.get("skills_requiring_validation", []),
                    "competency_breakdown": scores.get("competency_breakdown", {}),
                    "interview_readiness_level": narrative.get("interview_readiness_level") or scores.get("interview_readiness_level", "Ready for technical rounds"),
                    "technical_topics_to_revise": narrative.get("technical_topics_to_revise", []),
                    "communication_recommendations": narrative.get("communication_recommendations", []),
                    "recommendations": narrative.get("growth_areas", []) + narrative.get("communication_recommendations", []),
                    "hiring_recommendation": narrative["hiring_recommendation"],
                    "content_dimensions": scores["content_dimensions"],
                    "delivery_metrics": scores["delivery_metrics"],
                    "session_trends": scores["session_trends"],
                    "delivery_coaching": scores["delivery_coaching"],
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }

                # ── PERSIST IN NEON ───────────────────────────────────
                cur.execute(
                    """
                    UPDATE interviews
                    SET report = %s,
                        overall_score = %s,
                        category_scores = %s,
                        status = 'completed'
                    WHERE id = %s AND user_id = %s
                    """,
                    (
                        json.dumps(full_report),
                        scores["overall_score"],
                        json.dumps({
                            "technical": scores["technical_score"],
                            "clarity": scores["clarity_score"],
                            "confidence": scores["confidence_score"],
                        }),
                        session_id,
                        user_id
                    )
                )

        if ai_res:
            record_ai_usage("FINAL_REPORT", result=ai_res, interview_id=session_id, user_id=user_id)
        else:
            record_ai_usage("FINAL_REPORT", interview_id=session_id, user_id=user_id, status="fallback", model="fallback/heuristic")

        return full_report


# =====================================================================
# 4. TELEMETRY & COST AGGREGATION FUNCTIONS
# =====================================================================

def get_interview_ai_summary(interview_id: str) -> Dict[str, Any]:
    """
    Computes measured telemetry for a specific interview session.
    Returns real tokens, real cost, cache hits, and call counts.
    """
    with get_db() as conn:
        with dict_cursor(conn) as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*)                                          AS total_records,
                    COUNT(*) FILTER (WHERE cache_hit = FALSE)        AS ai_calls,
                    COUNT(*) FILTER (WHERE cache_hit = TRUE)         AS cache_hits,
                    COALESCE(SUM(input_tokens), 0)                   AS input_tokens,
                    COALESCE(SUM(output_tokens), 0)                  AS output_tokens,
                    COALESCE(SUM(total_tokens), 0)                   AS total_tokens,
                    COALESCE(SUM(estimated_cost), 0.0)               AS estimated_cost,
                    COALESCE(AVG(latency_ms), 0)                     AS avg_latency_ms,
                    COALESCE(SUM(retry_count), 0)                    AS retries
                FROM ai_usage
                WHERE interview_id = %s
                """,
                (interview_id,)
            )
            row = cur.fetchone()

    if not row or row["total_records"] == 0:
        return {
            "interview_id": interview_id,
            "ai_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "estimated_cost": 0.0,
            "cache_hits": 0,
            "retries": 0,
            "avg_latency_ms": 0,
            "data_status": "Unavailable",
        }

    return {
        "interview_id": interview_id,
        "ai_calls": int(row["ai_calls"]),
        "input_tokens": int(row["input_tokens"]),
        "output_tokens": int(row["output_tokens"]),
        "total_tokens": int(row["total_tokens"]),
        "estimated_cost": round(float(row["estimated_cost"]), 6),
        "cache_hits": int(row["cache_hits"]),
        "retries": int(row["retries"]),
        "avg_latency_ms": round(float(row["avg_latency_ms"]), 1),
        "data_status": "Measured",
    }


def get_admin_ai_metrics(
    period: str = "today",
    custom_start: Optional[str] = None,
    custom_end: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Computes authoritative AI analytics across the entire platform.
    Used for the admin-only AI cost dashboard.
    Filters: 'today', 'week', 'month', 'all', or custom ISO date range.
    """
    now = datetime.now(timezone.utc)
    if custom_start:
        try:
            since = datetime.fromisoformat(custom_start).replace(tzinfo=timezone.utc)
        except Exception:
            since = now - timedelta(days=7)
    elif period == "today":
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        since = now - timedelta(days=7)
    elif period == "month":
        since = now - timedelta(days=30)
    else:
        since = datetime(2020, 1, 1, tzinfo=timezone.utc)

    until = now
    if custom_end:
        try:
            until = datetime.fromisoformat(custom_end).replace(tzinfo=timezone.utc)
        except Exception:
            until = now

    with get_db() as conn:
        with dict_cursor(conn) as cur:
            # 1. Platform Totals & Percentiles
            cur.execute(
                """
                SELECT
                    COUNT(*)                                          AS total_records,
                    COUNT(*) FILTER (WHERE cache_hit = FALSE)        AS total_calls,
                    COUNT(*) FILTER (WHERE cache_hit = TRUE)         AS cache_hits,
                    COUNT(*) FILTER (WHERE status = 'fallback')      AS fallback_count,
                    COUNT(*) FILTER (WHERE retry_count > 0)          AS retry_occurrences,
                    COUNT(*) FILTER (WHERE truncation_detected = TRUE) AS truncation_count,
                    COALESCE(SUM(input_tokens), 0)                   AS total_input_tokens,
                    COALESCE(SUM(output_tokens), 0)                  AS total_output_tokens,
                    COALESCE(SUM(total_tokens), 0)                   AS total_tokens,
                    COALESCE(SUM(estimated_cost), 0.0)               AS total_estimated_cost,
                    COALESCE(AVG(latency_ms), 0)                     AS avg_latency_ms,
                    COALESCE(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY latency_ms), 0) AS p50_latency_ms,
                    COALESCE(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms), 0) AS p95_latency_ms,
                    COALESCE(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY latency_ms), 0) AS p99_latency_ms,
                    COALESCE(AVG(provider_latency_ms), 0)            AS avg_provider_latency_ms,
                    COALESCE(SUM(retry_delay_ms), 0)                 AS total_retry_delay_ms,
                    COALESCE(SUM(retry_count), 0)                    AS total_retries,
                    COUNT(DISTINCT interview_id)                     AS total_interviews
                FROM ai_usage
                WHERE created_at >= %s AND created_at <= %s
                """,
                (since, until)
            )
            totals = cur.fetchone()

            total_recs = int(totals["total_records"] or 0)
            total_calls = int(totals["total_calls"] or 0)
            cache_hits = int(totals["cache_hits"] or 0)
            fallback_cnt = int(totals["fallback_count"] or 0)
            trunc_cnt = int(totals["truncation_count"] or 0)
            total_ivs = max(1, int(totals["total_interviews"] or 0))

            cache_hit_rate = round((cache_hits / max(1, total_recs)) * 100, 1) if total_recs else 0.0
            retry_rate = round((int(totals["retry_occurrences"] or 0) / max(1, total_calls)) * 100, 1) if total_calls else 0.0
            fallback_rate = round((fallback_cnt / max(1, total_calls)) * 100, 1) if total_calls else 0.0
            truncation_rate = round((trunc_cnt / max(1, total_calls)) * 100, 1) if total_calls else 0.0

            avg_cost_iv = round(float(totals["total_estimated_cost"] or 0.0) / total_ivs, 6)
            avg_tok_iv = round(int(totals["total_tokens"] or 0) / total_ivs)
            avg_in_tok_iv = round(int(totals["total_input_tokens"] or 0) / total_ivs)
            avg_out_tok_iv = round(int(totals["total_output_tokens"] or 0) / total_ivs)
            avg_calls_iv = round(total_calls / total_ivs, 1)

            # 2. Breakdown by Request Type (With Output Token Ceiling Analysis)
            cur.execute(
                """
                SELECT
                    request_type,
                    COUNT(*)                                  AS count,
                    COUNT(*) FILTER (WHERE cache_hit = TRUE)  AS cache_hits,
                    COUNT(*) FILTER (WHERE retry_count > 0)   AS retries,
                    COUNT(*) FILTER (WHERE truncation_detected = TRUE) AS truncations,
                    COALESCE(SUM(input_tokens), 0)           AS input_tokens,
                    COALESCE(SUM(output_tokens), 0)          AS output_tokens,
                    COALESCE(AVG(output_tokens), 0)          AS avg_output_tokens,
                    COALESCE(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY output_tokens), 0) AS p50_output_tokens,
                    COALESCE(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY output_tokens), 0) AS p95_output_tokens,
                    COALESCE(MAX(output_tokens), 0)          AS max_output_tokens,
                    COALESCE(SUM(total_tokens), 0)           AS total_tokens,
                    COALESCE(SUM(estimated_cost), 0.0)       AS cost,
                    COALESCE(AVG(latency_ms), 0)             AS avg_latency_ms
                FROM ai_usage
                WHERE created_at >= %s AND created_at <= %s
                GROUP BY request_type
                ORDER BY total_tokens DESC
                """,
                (since, until)
            )
            by_request_type = []
            for r in cur.fetchall():
                rtype = r["request_type"]
                ceiling = get_max_output_tokens(rtype)
                avg_out = round(float(r["avg_output_tokens"]))
                util_pct = round((avg_out / max(1, ceiling)) * 100, 1)
                by_request_type.append({
                    "request_type": rtype,
                    "count": int(r["count"]),
                    "cache_hits": int(r["cache_hits"]),
                    "retries": int(r["retries"]),
                    "truncations": int(r["truncations"]),
                    "input_tokens": int(r["input_tokens"]),
                    "output_tokens": int(r["output_tokens"]),
                    "avg_output_tokens": avg_out,
                    "p50_output_tokens": round(float(r["p50_output_tokens"])),
                    "p95_output_tokens": round(float(r["p95_output_tokens"])),
                    "max_output_tokens": int(r["max_output_tokens"]),
                    "configured_ceiling": ceiling,
                    "ceiling_utilization_pct": util_pct,
                    "total_tokens": int(r["total_tokens"]),
                    "cost": round(float(r["cost"]), 6),
                    "avg_latency_ms": round(float(r["avg_latency_ms"]), 1),
                })

            # 3. Breakdown by Model
            cur.execute(
                """
                SELECT
                    model,
                    provider,
                    COUNT(*)                            AS count,
                    COUNT(*) FILTER (WHERE status = 'fallback') AS fallback_count,
                    COALESCE(SUM(total_tokens), 0)     AS total_tokens,
                    COALESCE(SUM(estimated_cost), 0.0) AS cost,
                    COALESCE(AVG(latency_ms), 0)       AS avg_latency_ms,
                    COALESCE(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms), 0) AS p95_latency_ms
                FROM ai_usage
                WHERE created_at >= %s AND created_at <= %s
                GROUP BY model, provider
                ORDER BY count DESC
                """,
                (since, until)
            )
            by_model = [
                {
                    "model": r["model"] or "unknown",
                    "provider": r["provider"] or "gemini",
                    "count": int(r["count"]),
                    "fallback_count": int(r["fallback_count"]),
                    "total_tokens": int(r["total_tokens"]),
                    "cost": round(float(r["cost"]), 6),
                    "avg_latency_ms": round(float(r["avg_latency_ms"]), 1),
                    "p95_latency_ms": round(float(r["p95_latency_ms"]), 1),
                }
                for r in cur.fetchall()
            ]

            # 4. Breakdown by Prompt Version
            cur.execute(
                """
                SELECT
                    prompt_version,
                    request_type,
                    COUNT(*)                                AS count,
                    COUNT(*) FILTER (WHERE validation_failed = TRUE) AS validation_failures,
                    COUNT(*) FILTER (WHERE retry_count > 0) AS retry_count,
                    COALESCE(AVG(input_tokens), 0)         AS avg_input_tokens,
                    COALESCE(AVG(output_tokens), 0)        AS avg_output_tokens,
                    COALESCE(AVG(total_tokens), 0)         AS avg_tokens,
                    COALESCE(SUM(total_tokens), 0)         AS total_tokens,
                    COALESCE(SUM(estimated_cost), 0.0)     AS cost,
                    COALESCE(AVG(latency_ms), 0)           AS avg_latency_ms
                FROM ai_usage
                WHERE created_at >= %s AND created_at <= %s
                GROUP BY prompt_version, request_type
                ORDER BY prompt_version DESC
                """,
                (since, until)
            )
            by_prompt_version = [
                {
                    "prompt_version": r["prompt_version"] or "v1",
                    "request_type": r["request_type"],
                    "count": int(r["count"]),
                    "validation_failures": int(r["validation_failures"]),
                    "retry_count": int(r["retry_count"]),
                    "avg_input_tokens": round(float(r["avg_input_tokens"])),
                    "avg_output_tokens": round(float(r["avg_output_tokens"])),
                    "avg_tokens": round(float(r["avg_tokens"])),
                    "total_tokens": int(r["total_tokens"]),
                    "cost": round(float(r["cost"]), 6),
                    "avg_latency_ms": round(float(r["avg_latency_ms"]), 1),
                }
                for r in cur.fetchall()
            ]

            # 5. Breakdown by Pricing Version (Reproducibility & Governance)
            cur.execute(
                """
                SELECT
                    pricing_version,
                    pricing_effective_date,
                    AVG(input_price_per_million) AS in_rate,
                    AVG(output_price_per_million) AS out_rate,
                    COUNT(*) AS count,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens,
                    COALESCE(SUM(estimated_cost), 0.0) AS cost
                FROM ai_usage
                WHERE created_at >= %s AND created_at <= %s
                GROUP BY pricing_version, pricing_effective_date
                ORDER BY pricing_version DESC
                """,
                (since, until)
            )
            by_pricing_version = [
                {
                    "pricing_version": r["pricing_version"] or "google_gemini_2026_01",
                    "effective_date": r["pricing_effective_date"] or "2026-01-01",
                    "input_price_per_million": round(float(r["in_rate"] or 0.10), 4),
                    "output_price_per_million": round(float(r["out_rate"] or 0.40), 4),
                    "count": int(r["count"]),
                    "total_tokens": int(r["total_tokens"]),
                    "cost": round(float(r["cost"]), 6),
                }
                for r in cur.fetchall()
            ]

            # 6. 7-Day Trend
            cur.execute(
                """
                SELECT
                    TO_CHAR(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD') AS day,
                    COUNT(*)                                             AS calls,
                    COALESCE(SUM(total_tokens), 0)                      AS tokens,
                    COALESCE(SUM(estimated_cost), 0.0)                  AS cost,
                    COUNT(DISTINCT interview_id)                         AS interviews
                FROM ai_usage
                WHERE created_at >= %s AND created_at <= %s
                GROUP BY TO_CHAR(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD')
                ORDER BY day ASC
                """,
                (now - timedelta(days=7), now)
            )
            by_day = [
                {
                    "day": r["day"],
                    "calls": int(r["calls"]),
                    "tokens": int(r["tokens"]),
                    "cost": round(float(r["cost"]), 6),
                    "interviews": int(r["interviews"] or 0),
                    "cost_per_interview": round(float(r["cost"]) / max(1, int(r["interviews"] or 1)), 4),
                }
                for r in cur.fetchall()
            ]

            # 7. Cost Anomaly Detection (1.5x rolling threshold check)
            anomalies = []
            if len(by_day) >= 2:
                recent_cost = by_day[-1]["cost"]
                prev_costs = [d["cost"] for d in by_day[:-1]]
                avg_prev = sum(prev_costs) / len(prev_costs)
                if avg_prev > 0 and recent_cost > (avg_prev * 1.5):
                    anomalies.append({
                        "type": "COST_SPIKE",
                        "message": f"Daily AI spend (${recent_cost:.4f}) is > 1.5x the rolling 7-day average (${avg_prev:.4f}).",
                        "severity": "warning",
                    })

            if retry_rate > 15.0:
                anomalies.append({
                    "type": "HIGH_RETRY_RATE",
                    "message": f"AI retry rate is {retry_rate}% (threshold is 15%). Inspect provider rate limits.",
                    "severity": "warning",
                })

    return {
        "period": period,
        "data_status": "Measured" if total_recs > 0 else "Unavailable",
        "total_ai_calls": total_calls,
        "total_calls": total_calls,
        "total_input_tokens": int(totals["total_input_tokens"] or 0),
        "total_output_tokens": int(totals["total_output_tokens"] or 0),
        "total_tokens": int(totals["total_tokens"] or 0),
        "total_estimated_cost": round(float(totals["total_estimated_cost"] or 0.0), 6),
        "estimated_cost": round(float(totals["total_estimated_cost"] or 0.0), 6),
        "average_cost_per_interview": avg_cost_iv,
        "average_tokens_per_interview": avg_tok_iv,
        "average_input_tokens_per_interview": avg_in_tok_iv,
        "average_output_tokens_per_interview": avg_out_tok_iv,
        "average_ai_calls_per_interview": avg_calls_iv,
        "avg_cost_per_interview": avg_cost_iv,
        "avg_tokens_per_interview": avg_tok_iv,
        "avg_calls_per_interview": avg_calls_iv,
        "average_latency_ms": round(float(totals["avg_latency_ms"] or 0.0), 1),
        "p50_latency_ms": round(float(totals["p50_latency_ms"] or 0.0), 1),
        "p95_latency_ms": round(float(totals["p95_latency_ms"] or 0.0), 1),
        "p99_latency_ms": round(float(totals["p99_latency_ms"] or 0.0), 1),
        "avg_provider_latency_ms": round(float(totals["avg_provider_latency_ms"] or 0.0), 1),
        "total_retry_delay_ms": int(totals["total_retry_delay_ms"] or 0),
        "cache_hit_rate": cache_hit_rate,
        "retry_rate": retry_rate,
        "fallback_rate": fallback_rate,
        "truncation_rate": truncation_rate,
        "by_request_type": by_request_type,
        "by_model": by_model,
        "by_prompt_version": by_prompt_version,
        "by_pricing_version": by_pricing_version,
        "by_day": by_day,
        "anomalies": anomalies,
        "model_routing_policy": model_router.get_routing_policy(),
    }


orchestrator = InterviewOrchestrator()
