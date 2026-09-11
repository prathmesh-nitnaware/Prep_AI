"""
backend/services/ai/schemas.py
==============================
Strict schemas and validation routines for structured AI outputs in PrepAI.
Enforces question-type-aware qualitative validation, STAR analysis,
technical depth levels, and deterministic scoring normalization.
"""
from typing import Any, Dict, List
from .exceptions import AIValidationError


def clamp_score(val: Any, min_val: int = 0, max_val: int = 10, default: int = 7) -> int:
    """Safely coerces any value to an integer within [min_val, max_val]."""
    try:
        if isinstance(val, (int, float)):
            n = int(round(val))
        elif isinstance(val, str) and val.strip().replace(".", "", 1).isdigit():
            n = int(round(float(val.strip())))
        else:
            return default
        return max(min_val, min(max_val, n))
    except Exception:
        return default


def ensure_list_of_strings(val: Any, default: List[str] = None) -> List[str]:
    """Ensures input is a clean list of strings."""
    if default is None:
        default = []
    if isinstance(val, list):
        return [str(x).strip() for x in val if x and str(x).strip()]
    if isinstance(val, str) and val.strip():
        return [val.strip()]
    return default


def validate_questions_output(data: Any, expected_count: int = 5) -> List[Dict[str, Any]]:
    """
    Validates question generation output array.
    Guarantees required fields and clean format.
    """
    if not isinstance(data, list):
        if isinstance(data, dict) and "questions" in data and isinstance(data["questions"], list):
            data = data["questions"]
        else:
            raise AIValidationError("Questions output must be a JSON array.")

    cleaned_questions: List[Dict[str, Any]] = []
    for idx, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            continue

        question_text = str(item.get("question") or item.get("title") or "").strip()
        if not question_text:
            continue

        q_type = str(item.get("question_type") or "technical").lower().strip()
        valid_types = ("technical", "system_design", "coding", "project", "behavioral", "situational", "hr", "mcq")
        if q_type not in valid_types:
            q_type = "technical"

        difficulty = str(item.get("difficulty") or "Medium").capitalize().strip()
        if difficulty not in ("Easy", "Medium", "Hard"):
            difficulty = "Medium"

        intent = str(item.get("intent") or item.get("reason") or "").strip()
        if not intent:
            if idx == 1: intent = "test_fundamentals"
            elif idx == 2: intent = "applied_scenario"
            elif idx == 3: intent = "test_tradeoff_reasoning"
            elif idx == 4: intent = "system_design"
            else: intent = "behavioral"

        cleaned_item: Dict[str, Any] = {
            "id": item.get("id") or idx,
            "question": question_text,
            "topic": str(item.get("topic") or item.get("category") or "General").strip(),
            "difficulty": difficulty,
            "question_type": q_type,
            "intent": intent,
            "expected_concepts": ensure_list_of_strings(item.get("expected_concepts") or item.get("expected_points")),
        }

        # Handle MCQ specific metadata if question_type is MCQ
        if q_type == "mcq":
            options = item.get("options") or []
            if isinstance(options, list) and len(options) >= 2:
                cleaned_item["options"] = [str(o).strip() for o in options]
                cleaned_item["correct_answer"] = str(item.get("correct_answer") or options[0]).strip()

        cleaned_questions.append(cleaned_item)

    if not cleaned_questions:
        raise AIValidationError("No valid questions could be extracted from AI response.")

    return cleaned_questions


def validate_answer_evaluation(data: Any) -> Dict[str, Any]:
    """
    Validates single answer qualitative evaluation output.
    Computes deterministic question-type-adapted content score from qualitative dimensions.
    """
    if not isinstance(data, dict):
        raise AIValidationError("Answer evaluation output must be a JSON object.")

    # 1. Qualitative Evaluation Dimensions (0-10)
    relevance = clamp_score(data.get("relevance"), 0, 10, default=7)
    technical_accuracy = clamp_score(data.get("technical_accuracy") or data.get("correctness"), 0, 10, default=7)
    depth = clamp_score(data.get("depth") or data.get("technical_depth"), 0, 10, default=7)
    completeness = clamp_score(data.get("completeness"), 0, 10, default=7)
    reasoning = clamp_score(data.get("reasoning") or data.get("clarity_score"), 0, 10, default=7)
    clarity = clamp_score(data.get("clarity") or data.get("clarity_score"), 0, 10, default=7)
    evidence = clamp_score(data.get("evidence"), 0, 10, default=7)

    # 2. Technical Depth Level (1 to 5)
    depth_level_raw = data.get("technical_depth_level") or data.get("depth_level")
    depth_level = clamp_score(depth_level_raw, 1, 5, default=3)

    # 3. Technical Errors List
    technical_errors = ensure_list_of_strings(data.get("technical_errors") or data.get("errors"))

    # 4. STAR Analysis (for behavioral / situational questions)
    star_raw = data.get("star_analysis") or {}
    if not isinstance(star_raw, dict):
        star_raw = {}
    
    star_situation = bool(star_raw.get("situation", False))
    star_task = bool(star_raw.get("task", False))
    star_action = bool(star_raw.get("action", False))
    star_result = bool(star_raw.get("result", False))
    star_elements_present = sum([star_situation, star_task, star_action, star_result])
    star_score = int(round((star_elements_present / 4.0) * 100))

    star_analysis = {
        "situation": star_situation,
        "task": star_task,
        "action": star_action,
        "result": star_result,
        "star_score": star_score,
    }

    # 5. Deterministic Content Score Computation
    q_type = str(data.get("question_type") or "technical").lower().strip()
    if q_type in ("behavioral", "situational", "hr"):
        weighted_points = (
            relevance * 0.15 +
            reasoning * 0.25 +
            clarity * 0.20 +
            (star_score / 10.0) * 0.40
        )
    elif q_type in ("system_design", "project"):
        weighted_points = (
            technical_accuracy * 0.30 +
            depth * 0.25 +
            reasoning * 0.20 +
            completeness * 0.15 +
            relevance * 0.10
        )
    else:  # standard technical / coding
        weighted_points = (
            technical_accuracy * 0.35 +
            depth * 0.25 +
            completeness * 0.15 +
            reasoning * 0.15 +
            relevance * 0.10
        )

    # Subtract minor deterministic penalty if factual technical errors are confirmed
    error_penalty = min(2.0, len(technical_errors) * 0.5)
    final_score_10 = max(1.0, min(10.0, weighted_points - error_penalty))
    final_score_100 = int(round(final_score_10 * 10))

    feedback = str(data.get("feedback") or "Response evaluated successfully.").strip()
    strengths = ensure_list_of_strings(data.get("strengths"), default=["Clear conceptual articulation"])
    improvements = ensure_list_of_strings(
        data.get("improvements") or data.get("weaknesses") or data.get("improvement"),
        default=["Add concrete implementation examples and quantifiable results"]
    )

    # 6. Action Recommendation & Validated Skills
    rec_action = str(data.get("recommended_next_action") or data.get("action") or "continue").lower().strip()
    valid_actions = ("probe_deeper", "increase_difficulty", "decrease_difficulty", "change_topic", "behavioral", "continue")
    if rec_action not in valid_actions:
        rec_action = "continue"

    missing_concepts = ensure_list_of_strings(data.get("missing_concepts") or data.get("missing_points"))
    technical_errors = ensure_list_of_strings(data.get("technical_errors") or data.get("errors"))
    tradeoffs_identified = ensure_list_of_strings(data.get("tradeoffs_identified") or data.get("trade_offs"))
    tradeoffs_missed = ensure_list_of_strings(data.get("tradeoffs_missed") or data.get("missed_tradeoffs"))
    validated_skills = ensure_list_of_strings(data.get("validated_skills") or data.get("skills_demonstrated"))
    recommended_follow_up = str(data.get("recommended_follow_up") or "").strip()
    evidence_summary = str(data.get("evidence_summary") or feedback).strip()

    return {
        "score": final_score_100,
        "score_10": int(round(final_score_10)),
        "relevance": relevance,
        "technical_accuracy": technical_accuracy,
        "correctness": technical_accuracy,
        "depth": depth,
        "technical_depth": depth,
        "completeness": completeness,
        "reasoning": reasoning,
        "clarity_score": clarity,
        "confidence_score": 8,  # System metadata confidence
        "evidence": evidence,
        "evidence_summary": evidence_summary,
        "technical_depth_level": depth_level,
        "technical_errors": technical_errors,
        "missing_concepts": missing_concepts,
        "tradeoffs_identified": tradeoffs_identified,
        "tradeoffs_missed": tradeoffs_missed,
        "validated_skills": validated_skills,
        "star_analysis": star_analysis,
        "recommended_next_action": rec_action,
        "recommended_follow_up": recommended_follow_up,
        "feedback": feedback,
        "strengths": strengths,
        "improvements": improvements,
    }


def validate_adaptive_question(data: Any) -> Dict[str, Any]:
    """
    Validates a single dynamic, adaptive interview question output.
    """
    if isinstance(data, list) and len(data) > 0:
        data = data[0]
    if not isinstance(data, dict):
        raise AIValidationError("Adaptive question output must be a JSON object.")

    question_text = str(data.get("question") or data.get("title") or "").strip()
    if not question_text:
        raise AIValidationError("Adaptive question missing question text.")

    q_type = str(data.get("question_type") or "technical").lower().strip()
    valid_types = ("technical", "system_design", "coding", "project", "behavioral", "situational", "hr")
    if q_type not in valid_types:
        q_type = "technical"

    difficulty_raw = data.get("difficulty")
    if isinstance(difficulty_raw, int):
        difficulty = clamp_score(difficulty_raw, 1, 5, default=3)
    elif str(difficulty_raw).isdigit():
        difficulty = clamp_score(int(difficulty_raw), 1, 5, default=3)
    else:
        difficulty = 3

    intent = str(data.get("intent") or data.get("reason") or "adaptive_inquiry").strip()

    return {
        "id": data.get("id") or 1,
        "question": question_text,
        "topic": str(data.get("topic") or "Adaptive Competency").strip(),
        "skill": str(data.get("skill") or "Technical Reasoning").strip(),
        "difficulty": difficulty,
        "question_type": q_type,
        "intent": intent,
        "expected_concepts": ensure_list_of_strings(data.get("expected_concepts")),
        "evaluation_criteria": ensure_list_of_strings(data.get("evaluation_criteria")),
        "follow_up_allowed": bool(data.get("follow_up_allowed", True)),
        "stage": str(data.get("stage") or "adaptive").strip(),
    }


def validate_final_report(data: Any) -> Dict[str, Any]:
    """
    Validates narrative final report output.
    Numeric metrics are calculated by backend; AI provides narrative interpretation.
    """
    if not isinstance(data, dict):
        raise AIValidationError("Final report output must be a JSON object.")

    summary = str(data.get("summary") or data.get("overview") or "Candidate completed the interview session.").strip()
    key_strengths = ensure_list_of_strings(data.get("key_strengths") or data.get("strengths"), default=["Demonstrated solid problem-solving foundation"])
    growth_areas = ensure_list_of_strings(data.get("growth_areas") or data.get("improvements") or data.get("weaknesses"), default=["Deepen architectural tradeoff justifications"])
    validated_skills = ensure_list_of_strings(data.get("validated_skills") or data.get("skills_validated"), default=["Core Engineering Fundamentals"])
    skills_requiring_validation = ensure_list_of_strings(data.get("skills_requiring_validation") or data.get("skills_to_improve"), default=["Distributed systems edge cases"])
    technical_topics = ensure_list_of_strings(data.get("technical_topics_to_revise") or data.get("topics_to_review"), default=["Core system architecture"])
    comm_recommendations = ensure_list_of_strings(data.get("communication_recommendations") or data.get("recommendations"), default=["Structure answers with clear problem-solution-impact flow"])
    readiness = str(data.get("interview_readiness_level") or "Ready for technical interview rounds").strip()
    hiring_recommendation = str(data.get("hiring_recommendation") or data.get("verdict") or "Recommended for further technical rounds").strip()

    return {
        "summary": summary,
        "key_strengths": key_strengths,
        "growth_areas": growth_areas,
        "validated_skills": validated_skills,
        "skills_requiring_validation": skills_requiring_validation,
        "technical_topics_to_revise": technical_topics,
        "communication_recommendations": comm_recommendations,
        "interview_readiness_level": readiness,
        "hiring_recommendation": hiring_recommendation,
    }


def validate_coding_evaluation(data: Any) -> Dict[str, Any]:
    """Validates code submission evaluation."""
    if not isinstance(data, dict):
        raise AIValidationError("Coding evaluation must be a JSON object.")
    success = bool(data.get("success", True))
    clarity = clamp_score(data.get("clarity_score") or data.get("clarity"), 0, 10, default=7)
    confidence = clamp_score(data.get("confidence_score") or data.get("confidence"), 0, 10, default=7)
    feedback = str(data.get("feedback") or "Code evaluated.").strip()
    suggestions = ensure_list_of_strings(data.get("suggestions") or data.get("improvements"))
    return {
        "success": success,
        "clarity_score": clarity,
        "confidence_score": confidence,
        "feedback": feedback,
        "suggestions": suggestions,
    }


def validate_resume_analysis(data: Any) -> Dict[str, Any]:
    """Validates resume scoring and extraction output."""
    if not isinstance(data, dict):
        raise AIValidationError("Resume analysis must be a JSON object.")
    
    raw_score = data.get("score") if data.get("score") is not None else data.get("ats_score")
    ats_score = clamp_score(raw_score, 0, 100, default=75)
    summary = str(data.get("summary") or "Resume parsed and evaluated.").strip()
    extracted_skills = ensure_list_of_strings(data.get("extracted_skills") or data.get("skills"))
    strengths = ensure_list_of_strings(data.get("strengths"))
    improvements = ensure_list_of_strings(data.get("improvements"))
    missing_keywords = ensure_list_of_strings(data.get("missing_keywords") or data.get("missing_skills"))
    
    cat_scores = data.get("category_scores") or {}
    if not isinstance(cat_scores, dict):
        cat_scores = {}

    category_scores = {
        "technical_skills_match": clamp_score(cat_scores.get("technical_skills_match"), 0, 100, default=min(100, max(30, ats_score + 2))),
        "experience_relevance": clamp_score(cat_scores.get("experience_relevance"), 0, 100, default=min(100, max(30, ats_score - 3))),
        "quantified_impact": clamp_score(cat_scores.get("quantified_impact"), 0, 100, default=min(100, max(25, ats_score - 10))),
        "formatting_ats_parseability": clamp_score(cat_scores.get("formatting_ats_parseability"), 0, 100, default=min(100, max(40, ats_score + 5))),
    }

    bullet_improvements = []
    raw_bullets = data.get("bullet_improvements")
    if isinstance(raw_bullets, list):
        for b in raw_bullets:
            if isinstance(b, dict) and b.get("original") and b.get("optimized"):
                bullet_improvements.append({
                    "original": str(b["original"]).strip(),
                    "optimized": str(b["optimized"]).strip()
                })

    interview_focus_areas = ensure_list_of_strings(data.get("interview_focus_areas"))

    return {
        "score": ats_score,
        "ats_score": ats_score,
        "summary": summary,
        "category_scores": category_scores,
        "extracted_skills": extracted_skills,
        "skills": extracted_skills,
        "strengths": strengths,
        "improvements": improvements,
        "missing_keywords": missing_keywords,
        "missing_skills": missing_keywords,
        "bullet_improvements": bullet_improvements,
        "interview_focus_areas": interview_focus_areas,
    }

