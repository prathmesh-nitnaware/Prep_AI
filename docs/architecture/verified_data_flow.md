# Verified Data Flow & Architectural Traces: PrepAI

**Date:** April 2026  
**Auditor:** Senior Backend Architect & AI Systems Engineer  
**Status:** 100% Verified against Source Code  

---

## 1. End-to-End Recording Data Flow & Runtime Crash Analysis

This trace documents the exact lifecycle of video/audio recordings from client capture to backend processing:

```
[Candidate Browser: InterviewLive.jsx]
   │
   ├─► navigator.mediaDevices.getUserMedia({video: true, audio: true})
   │      │
   │      ├─► MediaRecorder(stream, {mimeType: 'video/webm;codecs=vp9'})
   │      │      └─► ondataavailable (1000ms timeslices) -> recordedChunksRef.current[]
   │      │
   │      └─► Client Video HUD (In-browser Face-API & Web Audio API)
   │
   ▼ Interview Concludes (Question Count Reached or Early Exit)
finishAndProcessRecording()
   │
   ├─► Step 1: Local Candidate Download
   │      Blob(chunks, {type: 'video/webm'}) -> URL.createObjectURL(blob)
   │      <a download="PrepAI_Interview_<sessionId>.webm">.click()
   │      [SUCCESS: File is saved directly onto the candidate's local machine]
   │
   └─► Step 2: HTTP Network Upload
          api.uploadInterviewRecording(sessionId, blob)
          POST /api/interview/upload-recording (multipart/form-data)
          │
          ▼
   [Edge Reverse Proxy: Nginx]
          │
          ├─► client_max_body_size 15M;
          │      [RISK: Interviews >2-3 mins produce VP9 WebM files >15MB]
          │      [RESULT: Nginx terminates connection with HTTP 413 Request Entity Too Large]
          │
          ▼ If <= 15MB: Proxy Pass to Upstream (backend_1/2/3)
   [Flask WSGI Handler: routes/interview.py:upload_recording]
          │
          ├─► Line 335: session_id = request.form.get("session_id")
          ├─► Line 339: file = request.files["recording"]
          ├─► Line 350: SQL verification: SELECT id FROM interviews WHERE id = %s AND user_id = %s
          │
          ▼ Line 358: Directory Resolution
          recordings_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads", "recordings")
          │
          └──► CRITICAL DEFECT: `import os` is MISSING from routes/interview.py
                 │
                 ▼ Python Runtime Exception
                 NameError: name 'os' is not defined
                 │
                 ▼ Exception caught by generic handler (Line 377)
                 except Exception as e:
                     logger.error(f"Upload recording error: {e}")
                     return jsonify({"error": "Failed to upload session recording"}), 500
                 │
                 ▼ Client Browser (InterviewLive.jsx:171)
                 catch (err) { console.error('Error saving/downloading recording:', err); resolve(null); }
                 [RESULT: Server returns 500; frontend catches and swallows error; navigation continues to /report]
```

### Architectural Findings on Recording Flow:
1. **No Media Stored on Server:** Because `import os` is missing in [`backend/routes/interview.py:358`](file:///d:/Prep_AI/backend/routes/interview.py#L358), zero video recordings have ever been persisted to the server file system or database.
2. **Database Incomplete:** The `recording_url` column in the `interviews` table remains empty (`""`) for all sessions.
3. **Multi-Instance Storage Gap:** Even if `import os` is resolved, saving files to local disk `uploads/recordings/` inside Docker containers (`backend_1`, `backend_2`, `backend_3`) breaks in a multi-worker environment. Node 1 cannot serve files written by Node 2, and container restarts permanently destroy ephemeral disk state.

---

## 2. In-Browser Client Behavioral Signal Processing

Contrary to claims in `README.md` and `PROJECT_STATE.md` that Python MediaPipe and Librosa pipelines process candidate video and audio on the backend, **all behavioral telemetry runs entirely inside the client browser**:

```
[Candidate Webcam Stream]                      [Candidate Microphone Stream]
           │                                                │
           ▼                                                ▼
[@vladmandic/face-api in Browser]               [Web Audio API in Browser]
(TinyFaceDetector via WebGL/Wasm)             (AudioContext & AnalyserNode)
           │                                                │
           ├─► Face presence & bounding box                 ├─► RMS energy calculation
           ├─► 5 FPS temporal sampling                      ├─► Volume threshold detection
           ├─► Sustained gaze deviation frames              ├─► Silence duration tracking (>1.2s)
           └─► Posture stability score                      └─► Speaking pace & WPM calculation
           │                                                │
           └───────────────────────┬────────────────────────┘
                                   │
                                   ▼
                   [Aggregated Telemetry Payload]
                   signals: {
                       camera: {
                           face_present_ratio: 0.96,
                           proper_framing_ratio: 0.92,
                           gaze_alignment_score: 88,
                           excessive_movement_events: 1,
                           posture_stability_score: 90
                       },
                       voice: {
                           wpm: 138,
                           filler_word_count: 3,
                           pause_frequency: 4,
                           speaking_duration_ms: 24500,
                           silence_duration_ms: 4200
                       }
                   }
                                   │
                   Sent as JSON in POST /api/interview/submit
```

### Key Behavioral Invariants:
1. **Client Isolation:** Zero video frames or raw audio buffers leave the candidate's browser during the interview.
2. **Objective Metrics Only:** As specified in [`frontend/src/utils/cameraAnalytics.js:8`](file:///d:/Prep_AI/frontend/src/utils/cameraAnalytics.js#L8) and [`frontend/src/utils/voiceAnalytics.js:9`](file:///d:/Prep_AI/frontend/src/utils/voiceAnalytics.js#L9), the engines measure observable characteristics (framing, volume, duration, pause count) with **zero psychological or emotional inferences** (no claims of nervousness, honesty, or deception).

---

## 3. Mock Interview Lifecycle Data Flow

```
1. SETUP:
   GET /api/interview/resume-context
   Reads parsed resume text from users table if candidate previously uploaded one.

2. INITIATION:
   POST /api/interview/initiate
   Payload: {role, experience, focus, difficulty, resume_context, job_description, question_count}
   │
   ├─► InterviewOrchestrator.initiate_interview()
   ├─► Prompts Gemini (or Ollama fallback) with build_question_generation_prompt()
   ├─► Validates response with validate_questions_output()
   ├─► Generates deterministic interview stage strategy map
   ├─► INSERT INTO interviews (user_id, questions, strategy, status='active')
   ├─► INSERT INTO ai_usage (tokens, latency, pricing_version, cost)
   └─► Returns {session_id, first_question}

3. ANSWER SUBMISSION & SCORING:
   POST /api/interview/submit
   Payload: {session_id, question_id, question, answer, signals}
   │
   ├─► SQL: SELECT * FROM interviews WHERE id = %s FOR UPDATE (Row-level lock)
   ├─► Subjective Evaluation: Gemini executes build_answer_evaluation_prompt()
   ├─► Validates evaluation JSON with validate_answer_evaluation()
   ├─► Deterministic Fusion: Merges subjective score with camera/voice telemetry
   ├─► Computes running overall_score and category_scores
   ├─► Appends evaluated answer to interviews.answers JSONB array
   ├─► INSERT INTO ai_usage
   └─► Returns {feedback: {score, clarity, technical, confidence, ideal_answer}}

4. ADAPTIVE PROGRESSION:
   POST /api/interview/next
   Payload: {session_id, current_index}
   │
   ├─► Reads stage strategy from interviews.strategy
   ├─► Prompts Gemini for stage-calibrated follow-up (build_adaptive_next_question_prompt)
   ├─► Validates question with validate_adaptive_question()
   └─► Returns next question or completed: true

5. REPORT GENERATION:
   POST /api/interview/complete or GET /api/interview/report/<session_id>
   │
   ├─► Checks interviews.report (returns immediately if already cached)
   ├─► If ungenerated: Prompts Gemini with build_final_report_prompt()
   ├─► Validates with validate_final_report()
   ├─► UPDATE interviews SET report = %s, status = 'completed'
   └─► Returns final structured scorecard
```

---

## 4. Resume Scoring Flow (`POST /api/resume/score`)

```
Candidate Uploads PDF/DOCX/TXT
   │
   ▼ POST /api/resume/score
backend/routes/resume_score.py:score_resume()
   │
   ├─► Validate file extension (.pdf, .docx, .txt) & size (<= 10MB)
   ├─► Save to tempfile.NamedTemporaryFile
   ├─► Extract raw text via PyMuPDF (fitz)
   ├─► Clean up temp file
   │
   ▼ AI Processing
services/ai/gemini_service.py:execute_structured_request()
   │
   ├─► Build prompt: build_resume_analysis_prompt(resume_text, role, job_description)
   ├─► Model Router selects: gemini-2.0-flash (max output tokens: 1500)
   ├─► Call Google GenAI SDK (models.generate_content)
   │      └─► On failure: retries with exponential backoff; falls back to Ollama or heuristic dict
   ├─► Validate response schema: validate_resume_analysis()
   ├─► Log telemetry: INSERT INTO ai_usage
   │
   ▼ Database Persistence
INSERT INTO resumes (user_id, role, score, summary)
   │
   ▼ Return JSON Response (Exact contract preserved)
{
  "score": 75,
  "summary": "...",
  "category_scores": {...},
  "extracted_skills": [...],
  "strengths": [...],
  "weaknesses": [...],
  "items_to_delete": [...],
  "bullet_improvements": [...]
}
```

---

## 5. Coding Dojo Flow (`POST /api/coding/submit`)

```
Candidate Submits Code from Monaco Editor
   │
   ▼ POST /api/coding/submit
backend/routes/coding.py:submit_challenge()
   │
   ├─► Validate payload (code length <= 50KB, challenge_id exists)
   ├─► Fetch challenge title & description from in-memory CHALLENGES array
   │
   ▼ AI Review (No Local Code Execution Sandbox)
services/ai/gemini_service.py:execute_structured_request()
   │
   ├─► Build prompt: build_coding_evaluation_prompt(title, desc, code, language)
   ├─► Model Router selects: gemini-2.0-flash (max output tokens: 350)
   ├─► Gemini reviews code logic, edge cases, space/time complexity
   ├─► Validate response: validate_coding_evaluation()
   ├─► Log telemetry: INSERT INTO ai_usage
   │
   ▼ Database Persistence
If action == "submit":
   INSERT INTO coding_submissions (user_id, challenge_id, code, success, clarity_score, ...)
   │
   ▼ Return JSON Feedback
{
  "success": true,
  "clarity_score": 8,
  "confidence_score": 8,
  "feedback": "...",
  "suggestions": [...]
}
```

---

## 6. AI Telemetry & Cost Governance Flow

```
Any AI Invocation Across Platform
   │
   ▼ services/ai/gemini_service.py:execute_structured_request()
Captures raw token usage from Google GenAI response.usage_metadata:
   - prompt_token_count -> input_tokens
   - candidates_token_count -> output_tokens
   - total_token_count -> total_tokens
   │
   ▼ pricing.py:calculate_token_cost()
Resolves pricing version metadata ("google_gemini_2026_01", effective 2026-01-01):
   - input_cost = (input_tokens / 1,000,000) * $0.10
   - output_cost = (output_tokens / 1,000,000) * $0.40
   - estimated_cost = input_cost + output_cost
   │
   ▼ orchestrator.py:record_ai_usage()
INSERT INTO ai_usage (
    request_type, model, provider, prompt_version, pricing_version,
    input_tokens, output_tokens, total_tokens, input_cost, output_cost, estimated_cost,
    latency_ms, provider_latency_ms, retry_delay_ms, retry_count,
    cache_hit, validation_failed, truncation_detected
)
   │
   ▼ Admin Query: GET /api/admin/ai/metrics?period=today
Aggregates total tokens, total spend, latency percentiles, cost anomalies for admin panel.
```

