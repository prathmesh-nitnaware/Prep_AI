# PrepAI Dependency & AI Integration Audit

**Date:** April 2026  
**Auditor:** Senior Backend Architect & AI Systems Engineer (PIE R0 Read-Only Audit)  
**Status:** Baseline Completed  

---

## 1. Executive Summary

This audit catalogs all external and internal AI/LLM integrations, model dependencies, APIs, and client-side model runtimes across the PrepAI codebase. Every integration has been verified by examining the actual source code rather than documentation claims.

Key takeaways:
1. **Primary Production LLM:** Google Gemini (`gemini-2.0-flash`) via the modern `google-genai` SDK (`genai.Client`).
2. **Fallback LLM:** Ollama (`llama3:8b`) via the official `ollama` Python SDK (`ollama.Client`).
3. **Dead / Unused AI Wrappers:** `backend/utils/ai_client.py` and `backend/app/providers/` (`AIFactory`, `OllamaProvider`) are orphan legacy implementations never invoked by active routes.
4. **Broken NLP Scripts:** `ml/nlp/resume_parser.py` attempts to import a non-existent `backend.ollama_client` and will crash upon import.
5. **Computer Vision & Audio ML in `/ml`:** Scripts in `ml/` (`eye_tracking.py`, `posture_analysis.py`, `emotion_detector.py`) are research prototypes and are **not** wired into any backend routes or production data paths.
6. **Active Client-Side Vision & Audio:** All real-time face detection, head gaze stability, and voice silence/pause monitoring are performed **entirely client-side in the browser** using `@vladmandic/face-api` (TinyFaceDetector) and Web Audio API. No video frames or audio streams are transmitted to the backend.

---

## 2. Comprehensive Integration Inventory

| Provider / Technology | File Path | Calling Function | Purpose | Application Workflow | Invocation Style | Environment Variables | Current Status | Migration Priority to PIE |
|---|---|---|---|---|---|---|---|---|
| **Google GenAI** (`gemini-2.0-flash`) | `backend/services/ai/gemini_service.py` | `GeminiService._call_provider` | Structured generation for questions, answer evaluations, final reports, coding reviews, resume scoring, chatbot | Central AI gateway for all 6 active AI workflows | Direct (`gemini_client.models.generate_content`) | `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_QUESTION_MODEL`, `GEMINI_EVALUATION_MODEL`, `GEMINI_REPORT_MODEL` | **Active (Primary)** | **High** (Isolate into legacy baseline; decouple from PIE core) |
| **Google GenAI** (`gemini-2.0-flash`) | `backend/services/ai/gemini_service.py` | `GeminiService.stream_response` | Token streaming over WebSocket for live interview chat | Real-time WebSocket interview chat (`/api/v1/interview/stream`) | Streaming (`models.generate_content_stream`) | `GEMINI_API_KEY`, `GEMINI_MODEL` | **Active (WebSocket)** | **Medium** (Preserve in legacy until R5) |
| **Ollama** (`llama3:8b`) | `backend/services/ai/gemini_service.py` | `GeminiService._call_ollama_fallback` | Local fallback when Gemini fails, times out, or hits rate limits | Fallback for question generation, evaluation, reports, coding, resume | Direct (`ollama_client.chat`) | `OLLAMA_HOST`, `OLLAMA_MODEL`, `AI_PROVIDER` | **Active (Fallback)** | **Medium** (Classify as local baseline adapter) |
| **Ollama** (`llama3:8b`) | `backend/services/ai/gemini_service.py` | `GeminiService.stream_response` | Local streaming fallback for WebSocket when Gemini streaming fails | Real-time WebSocket interview chat | Streaming (`ollama_client.chat(stream=True)`) | `OLLAMA_HOST`, `OLLAMA_MODEL` | **Active (Fallback)** | **Medium** (Classify as local baseline) |
| **Ollama** (`llama3:8b`) | `backend/utils/ai_client.py` | `generate_question`, `AIClient.chat` | Unused legacy question generation and chat helper | None (Orphan file) | Direct (`ollama.chat`) | None (Hardcoded `llama3:8b`) | **Unused / Dead** | **Low** (Deprecate / Archive) |
| **Ollama** (`llama3:8b`) | `backend/app/providers/ollama_provider.py` | `OllamaProvider.ask`, `stream` | Unused factory-based provider wrapper | None (Orphan file) | Direct (`ollama.Client`) | `OLLAMA_HOST`, `OLLAMA_MODEL` | **Unused / Dead** | **Low** (Deprecate / Archive) |
| **AIFactory** | `backend/app/providers/factory.py` | `AIFactory.get_provider` | Unused factory intended to switch between Ollama and Gemini | None (Orphan file) | N/A | `AI_PROVIDER` | **Unused / Dead** | **Low** (Deprecate / Archive) |
| **RapidAPI Judge0** | `backend/app/services/judge_service.py` | `JudgeService.execute` | Remote code execution API sandbox | Coding Dojo (never wired; coding uses LLM evaluation instead) | HTTP POST to `judge0-ce.p.rapidapi.com` | Hardcoded `API_KEY = "REPLACE_WITH_YOUR_KEY"` | **Unused / Dead** | **Low** (Do not use; sandbox deferred to R3) |
| **spaCy + Ollama** | `ml/nlp/resume_parser.py` | `parse_resume_with_ollama`, `parse_resume_with_spacy` | Entity matching and resume parsing | Legacy prototype (broken import `from backend.ollama_client`) | Direct script execution | None | **Broken / Dead** | **Low** (Do not import) |
| **Procedural Question Engine** | `backend/services/ai/local_question_engine.py` | `LocalQuestionEngine.generate_session_questions` | Dynamic, non-repeating 5-stage placement questions grounded in resume & JD | Untracked experimental local question generator | Direct deterministic procedural algorithm | None | **Untracked / Experimental** | **Medium** (Candidate component for future deterministic modules) |
| **Procedural ATS Engine** | `ml/nlp/resume_engine.py` | `ResumeEngine.parse_profile`, `score_ats` | Fast regex taxonomy skill matcher and ATS scorer | Untracked experimental resume scorer | Direct deterministic procedural algorithm | None | **Untracked / Experimental** | **High** (High-value deterministic logic for PIE R1) |
| **MediaPipe / OpenCV** | `ml/cv/eye_tracking.py`, `ml/cv/posture_analysis.py` | `get_head_pose`, `calculate_posture_score` | 3D head pose via solvePnP, blink detection, shoulder tilt | Standalone research prototypes | Direct script execution | None | **Unused Prototype** | **Low** (Reference only for R4) |
| **Librosa Signal Processing** | `ml/audio/emotion_detector.py` | `analyze_audio_features` | RMS energy, pyin pitch jitter, speech/silence split | Standalone research prototype | Direct script execution | None | **Unused Prototype** | **Low** (Reference only for R4) |
| **Client-Side Face-API** | `frontend/src/utils/cameraAnalytics.js` | `CameraAnalyticsEngine.analyzeFrame` | Real-time face detection, framing, gaze alignment, movement stability | Live interview browser HUD & telemetry payload | In-browser Wasm/WebGL (`@vladmandic/face-api`) | None | **Active (Client-side)** | **Keep in frontend** (Payload consumed deterministically) |
| **Client-Side Web Audio API** | `frontend/src/utils/voiceAnalytics.js` | `VoiceAnalyticsEngine.processAudioSample` | Deterministic WPM, pause frequency, filler word count, speaking duration | Live interview browser HUD & telemetry payload | In-browser Web Audio API | None | **Active (Client-side)** | **Keep in frontend** (Payload consumed deterministically) |
| **HTML5 Web Speech** | `frontend/src/pages/InterviewLive.jsx` | `webkitSpeechRecognition`, `window.speechSynthesis` | Voice-to-text input and text-to-speech audio question readout | Live interview speech input/output | In-browser native browser APIs | None | **Active (Client-side)** | **Keep in frontend** |

---

## 3. Workflow-to-AI Provider Mapping

### Workflow A: Mock Interview Generation (`POST /api/interview/initiate`)
- **Orchestrator:** `InterviewOrchestrator.initiate_interview()` in `backend/services/ai/orchestrator.py`
- **Prompt:** `build_question_generation_prompt()` in `backend/services/ai/prompts.py`
- **Primary Provider:** `GeminiService` -> `gemini-2.0-flash`
- **Fallback Provider:** `ollama/llama3:8b`
- **Output Validation:** `validate_questions_output()` in `backend/services/ai/schemas.py`
- **Database Write:** Session and questions saved to `interviews` table; usage to `ai_usage` table.

### Workflow B: Adaptive Question Generation (`POST /api/interview/next`)
- **Orchestrator:** `InterviewOrchestrator.get_or_generate_next_question()`
- **Prompt:** `build_adaptive_next_question_prompt()`
- **Primary Provider:** `gemini-2.0-flash` (max output tokens: 350)
- **Fallback Provider:** `ollama/llama3:8b`
- **Output Validation:** `validate_adaptive_question()`

### Workflow C: Answer Evaluation (`POST /api/interview/submit`)
- **Orchestrator:** `InterviewOrchestrator.evaluate_and_submit_answer()`
- **Prompt:** `build_answer_evaluation_prompt()`
- **Primary Provider:** `gemini-2.0-flash` (max output tokens: 350)
- **Fallback Provider:** `ollama/llama3:8b`
- **Output Validation:** `validate_answer_evaluation()`
- **Deterministic Layer:** Mathematical score aggregation, objective verification, camera/voice signals fusion.

### Workflow D: Final Report Generation (`POST /api/interview/complete`, `GET /api/interview/report/<session_id>`)
- **Orchestrator:** `InterviewOrchestrator.get_or_generate_final_report()`
- **Prompt:** `build_final_report_prompt()`
- **Primary Provider:** `gemini-2.0-flash` (max output tokens: 512)
- **Fallback Provider:** `ollama/llama3:8b`
- **Output Validation:** `validate_final_report()`

### Workflow E: Resume Scoring (`POST /api/resume/score`)
- **Route:** `backend/routes/resume_score.py:score_resume`
- **Text Extraction:** PyMuPDF (`fitz`) via `utils.resume_parser.extract_text_from_file`
- **Prompt:** `build_resume_analysis_prompt()`
- **Primary Provider:** `gemini-2.0-flash` (max output tokens: 1500)
- **Fallback:** Heuristic dictionary fallback with default scores when AI call fails.
- **Output Validation:** `validate_resume_analysis()`
- **Database Write:** Record saved to `resumes` table; usage to `ai_usage` table.

### Workflow F: Coding Dojo Evaluation (`POST /api/coding/submit`)
- **Route:** `backend/routes/coding.py:submit_challenge`
- **Execution Mechanism:** **No code execution sandbox.** The user code is embedded in an AI prompt (`build_coding_evaluation_prompt`) and evaluated by Gemini/Ollama.
- **Primary Provider:** `gemini-2.0-flash` (max output tokens: 350)
- **Fallback:** Static feedback dictionary.
- **Database Write:** Submission saved to `coding_submissions` table; usage to `ai_usage` table.

### Workflow G: Support Chatbot (`POST /api/chatbot/ask`)
- **Route:** `backend/routes/chatbot.py:ask_chatbot`
- **Prompt:** Inline system prompt defining PrepAI platform scope.
- **Primary Provider:** `gemini-2.0-flash` (max output tokens: 200)
- **Fallback:** Static friendly greeting.
- **Database Write:** Usage logged to `ai_usage` table.

### Workflow H: Real-time Audio WebSocket Stream (`/api/v1/interview/stream`)
- **Handler:** `backend/app/controllers/interview_socket.py:interview_stream`
- **Primary Provider:** `gemini_service.stream_response()`
- **Fallback:** Ollama streaming or static prompt.

---

## 4. Key AI Governance & Cost Management Infrastructure

The backend already contains an advanced AI governance layer implemented in `backend/services/ai/`:
- **Central Model Router (`router.py`):** Configurable per-task routing (`AIModelRouter`) mapping `QUESTION_GENERATION`, `ANSWER_EVALUATION`, `FINAL_REPORT`, `RESUME_SCORING`, `CODING_EVALUATION`, and `CHATBOT_ASSIST`.
- **Pricing Versioning & Cost Calculation (`pricing.py`):** Fixed pricing metadata table (`google_gemini_2026_01`) recording per-million input/output token pricing, effective dates, and computing fractional-cent costs.
- **Output Token Ceilings (`pricing.py`):** Request-specific token limits preventing runaway token generation.
- **Prompt Versioning (`pricing.py`):** Tracked prompt identifiers (`question_generation_v2`, `resume_scoring_v2`, etc.).
- **Telemetry Persistence (`orchestrator.py:record_ai_usage`):** Every AI invocation persists input tokens, output tokens, latency breakdown (provider vs total), retry counts, cache hits, and pricing version into the `ai_usage` table.
- **Admin Telemetry Endpoint (`routes/admin.py:get_ai_metrics`):** Aggregates platform spend, token consumption, and cost anomalies over time.

---

## 5. Architectural Implications for PIE R0

1. **Strict Decoupling Required:** PIE must not invoke `gemini_service` or `ollama` directly for its production execution paths.
2. **Baseline Classification:** Existing Gemini and Ollama providers must be classified as `baseline_only` in the PIE model registry.
3. **No Network Access in Unit Tests:** All PIE tests must execute with zero external HTTP/socket calls.
4. **Step 9 First Migration Candidate:** `POST /api/resume/score` is an ideal candidate for R0's `LegacyResumeModule` adapter because it is a self-contained single-call endpoint that parses a document, calculates scores, and persists to the database.

