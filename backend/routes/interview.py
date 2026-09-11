"""
routes/interview.py — Interview routes using Neon PostgreSQL & Interview Orchestrator
====================================================================================
Hybrid AI + Deterministic Business Logic Architecture:
- Single-call structured question generation
- Isolated single-answer subjective evaluation
- Deterministic objective/MCQ verification & mathematical scoring
- Single-call narrative report generation with persistent caching
- Idempotency & duplicate submission protection
"""
import json
import logging
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from utils.auth_helpers import token_required
from utils.middleware import rate_limit, cache_response, invalidate_user_cache
from extensions import get_db, dict_cursor
from services.ai.orchestrator import orchestrator, calculate_interview_scores
from models.user_model import get_user_by_id

logger = logging.getLogger(__name__)
interview_bp = Blueprint("interview", __name__)


def _row_to_dict(row: dict) -> dict:
    """Serialize a DB row — converts UUID → str, datetime → ISO string."""
    if not row:
        return {}
    result = {}
    for k, v in row.items():
        if hasattr(v, "hex"):           # UUID
            result[k] = str(v)
        elif hasattr(v, "isoformat"):   # datetime
            result[k] = v.isoformat()
        else:
            result[k] = v
    return result


# ── GET RESUME CONTEXT ──────────────────────────────────────
@interview_bp.route("/resume-context", methods=["GET"])
@token_required
def get_resume_context(current_user):
    user = get_user_by_id(str(current_user["id"]))
    if user and user.get("resume_text"):
        return jsonify({
            "has_resume": True,
            "resume_text": user["resume_text"],
            "resume_filename": user.get("resume_filename")
        }), 200
    return jsonify({
        "has_resume": False,
        "resume_text": "",
        "resume_filename": None
    }), 200


# ── INITIATE SESSION ────────────────────────────────────────
@interview_bp.route("/initiate", methods=["POST"])
@token_required
@rate_limit
def initiate_session(current_user):
    try:
        data = request.get_json(silent=True)
        if data is None:
            return jsonify({"error": "Missing or malformed JSON body"}), 400

        role = str(data.get("role", "Software Engineer"))[:100]
        experience = str(data.get("experience", "Mid-Level"))[:50]
        focus = str(data.get("focus", "General"))[:100]
        difficulty = str(data.get("difficulty", "Medium"))[:50]
        resume_ctx = str(data.get("resume_context", ""))[:2000]
        job_description = str(data.get("job_description", data.get("jd", "")))[:4000]
        question_count = min(15, max(3, int(data.get("question_count", data.get("intensity", 5)))))

        session, questions = orchestrator.initiate_interview(
            user_id=str(current_user["id"]),
            role=role,
            experience=experience,
            focus=focus,
            difficulty=difficulty,
            resume_ctx=resume_ctx,
            question_count=question_count,
            job_description=job_description,
        )

        first_q = questions[0] if questions else {}

        return jsonify({
            "session": session,
            "session_id": session.get("id"),
            "question": first_q,
            "first_question": first_q
        }), 200

    except Exception as e:
        logger.error(f"Initiate session error: {e}")
        return jsonify({"error": "Failed to initiate interview session"}), 500


# ── SUBMIT ANSWER ───────────────────────────────────────────
@interview_bp.route("/submit", methods=["POST"])
@token_required
@rate_limit
def submit_answer(current_user):
    try:
        data = request.get_json(silent=True)
        if data is None:
            return jsonify({"error": "Missing or malformed JSON body"}), 400

        session_id = data.get("session_id")
        raw_question = data.get("question", {})
        question_id = data.get("question_id")
        answer = str(data.get("answer", "")).strip()[:5000]
        signals = data.get("signals") or data.get("voice_metrics")
        user_id = str(current_user["id"])

        if not session_id:
            return jsonify({"error": "session_id is required"}), 400

        if isinstance(raw_question, str):
            question_dict = {"id": question_id or 1, "question": raw_question, "title": raw_question}
        elif isinstance(raw_question, dict):
            question_dict = dict(raw_question)
            if "id" not in question_dict and question_id:
                question_dict["id"] = question_id
        else:
            question_dict = {"id": question_id or 1, "question": str(raw_question)}

        feedback = orchestrator.evaluate_and_submit_answer(
            session_id=session_id,
            user_id=user_id,
            question_data=question_dict,
            answer_text=answer,
            signals=signals,
        )

        return jsonify({"feedback": feedback}), 200

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 404
    except Exception as e:
        logger.error(f"Submit answer error: {e}")
        return jsonify({"error": "Failed to submit answer"}), 500


# ── NEXT QUESTION (Adaptive & Strategy-Aware) ───────────────
@interview_bp.route("/next", methods=["POST"])
@token_required
@rate_limit
def next_question(current_user):
    try:
        data = request.get_json(silent=True)
        if data is None:
            return jsonify({"error": "Missing or malformed JSON body"}), 400

        session_id = data.get("session_id")
        current_index = int(data.get("current_index", data.get("current_question_index", 0)))
        user_id = str(current_user["id"])

        if not session_id:
            return jsonify({"error": "session_id is required"}), 400

        result = orchestrator.get_or_generate_next_question(
            session_id=session_id,
            user_id=user_id,
            current_index=current_index,
        )

        return jsonify(result), 200

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 404
    except Exception as e:
        logger.error(f"Next question error: {e}")
        return jsonify({"error": "Failed to fetch next question"}), 500


# ── COMPLETE SESSION & GENERATE REPORT ──────────────────────
@interview_bp.route("/complete", methods=["POST"])
@token_required
@rate_limit
def complete_session(current_user):
    try:
        data = request.get_json(silent=True)
        if data is None:
            return jsonify({"error": "Missing or malformed JSON body"}), 400

        session_id = data.get("session_id")
        user_id = str(current_user["id"])

        if not session_id:
            return jsonify({"error": "session_id is required"}), 400

        report = orchestrator.get_or_generate_final_report(
            session_id=session_id,
            user_id=user_id,
        )

        invalidate_user_cache(user_id)
        return jsonify({"success": True, "report": report}), 200

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 404
    except Exception as e:
        logger.error(f"Complete session error: {e}")
        return jsonify({"error": "Failed to generate interview report"}), 500


# ── GET FINAL REPORT ─────────────────────────────────────────
@interview_bp.route("/report/<session_id>", methods=["GET"])
@interview_bp.route("/session/<session_id>/report", methods=["GET"])
@token_required
def get_final_report(current_user, session_id):
    try:
        user_id = str(current_user["id"])
        report = orchestrator.get_or_generate_final_report(
            session_id=session_id,
            user_id=user_id,
        )
        return jsonify({"report": report, "success": True}), 200
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 404
    except Exception as e:
        logger.error(f"Get final report error: {e}")
        return jsonify({"error": "Failed to fetch report"}), 500


# ── GET INTERVIEW AI TELEMETRY (Phase 4) ──────────────────────
@interview_bp.route("/session/<session_id>/telemetry", methods=["GET"])
@token_required
def get_session_telemetry(current_user, session_id):
    try:
        user_id = str(current_user["id"])
        with get_db() as conn:
            with dict_cursor(conn) as cur:
                cur.execute(
                    "SELECT id FROM interviews WHERE id = %s AND user_id = %s",
                    (session_id, user_id)
                )
                if not cur.fetchone():
                    return jsonify({"error": "Interview session not found or access denied"}), 404

        from services.ai.orchestrator import get_interview_ai_summary
        summary = get_interview_ai_summary(session_id)
        return jsonify(summary), 200
    except Exception as e:
        logger.error(f"Get session telemetry error: {e}")
        return jsonify({"error": "Failed to fetch interview telemetry"}), 500


# ── HISTORY ─────────────────────────────────────────────────
@interview_bp.route("/history", methods=["GET"])
@token_required
@cache_response(ttl=45)
def get_history(current_user):
    try:
        with get_db() as conn:
            with dict_cursor(conn) as cur:
                cur.execute(
                    """
                    SELECT id, role, experience, difficulty, status, overall_score, category_scores, created_at
                    FROM interviews
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    """,
                    (str(current_user["id"]),)
                )
                rows = cur.fetchall()

        history = [_row_to_dict(r) for r in rows]
        return jsonify(history), 200

    except Exception as e:
        logger.error(f"Get history error: {e}")
        return jsonify({"error": str(e)}), 500


# ── DELETE SESSION ───────────────────────────────────────────
@interview_bp.route("/delete/<session_id>", methods=["DELETE"])
@token_required
def delete_session(current_user, session_id):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM interviews WHERE id = %s AND user_id = %s",
                    (session_id, str(current_user["id"]))
                )

        invalidate_user_cache(str(current_user["id"]))
        return jsonify({"success": True}), 200

    except Exception as e:
        logger.error(f"Delete session error: {e}")
        return jsonify({"error": str(e)}), 500


# ── GET SESSION ──────────────────────────────────────────────
@interview_bp.route("/session/<session_id>", methods=["GET"])
@token_required
def get_session(current_user, session_id):
    try:
        with get_db() as conn:
            with dict_cursor(conn) as cur:
                cur.execute(
                    "SELECT * FROM interviews WHERE id = %s AND user_id = %s",
                    (session_id, str(current_user["id"]))
                )
                row = cur.fetchone()

        if not row:
            return jsonify({"error": "Session not found"}), 404

        session = _row_to_dict(row)
        if isinstance(session.get("questions"), str):
            session["questions"] = json.loads(session["questions"])
        if isinstance(session.get("answers"), str):
            session["answers"] = json.loads(session["answers"])
        if isinstance(session.get("report"), str):
            session["report"] = json.loads(session["report"])

        return jsonify(session), 200

    except Exception as e:
        logger.error(f"Get session error: {e}")
        return jsonify({"error": str(e)}), 500


# ── UPLOAD SESSION RECORDING ────────────────────────────────
@interview_bp.route("/upload-recording", methods=["POST"])
@token_required
def upload_recording(current_user):
    try:
        session_id = request.form.get("session_id")
        if not session_id:
            return jsonify({"error": "session_id is required"}), 400

        if "recording" not in request.files:
            return jsonify({"error": "No recording file uploaded"}), 400

        file = request.files["recording"]
        if not file or not file.filename:
            return jsonify({"error": "Empty recording file"}), 400

        user_id = str(current_user["id"])
        
        # Verify session ownership
        with get_db() as conn:
            with dict_cursor(conn) as cur:
                cur.execute(
                    "SELECT id FROM interviews WHERE id = %s AND user_id = %s",
                    (session_id, user_id)
                )
                if not cur.fetchone():
                    return jsonify({"error": "Interview session not found or unauthorized"}), 404

        recordings_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads", "recordings")
        os.makedirs(recordings_dir, exist_ok=True)

        filename = f"recording_{session_id}.webm"
        file_path = os.path.join(recordings_dir, filename)
        file.save(file_path)

        relative_url = f"/uploads/recordings/{filename}"

        # Update database with recording URL
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE interviews SET recording_url = %s WHERE id = %s AND user_id = %s",
                    (relative_url, session_id, user_id)
                )

        return jsonify({"success": True, "recording_url": relative_url}), 200

    except Exception as e:
        logger.error(f"Upload recording error: {e}")
        return jsonify({"error": "Failed to upload session recording"}), 500