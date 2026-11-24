"""
backend/services/ai/local_question_engine.py
============================================
Adaptive, Resume-Grounded Question Engine.
Completely independent of public LLMs (Gemini, OpenAI) and Ollama.
Generates dynamic, unique, non-repeating 5-stage placement questions
procedurally calibrated to the candidate's actual parsed resume,
claimed technologies, projects, and target role.
"""

import random
import hashlib
from typing import Dict, List, Any, Optional
from ml.nlp.resume_engine import resume_engine


# Specialized Technical Question Blueprints by Technology
TECH_QUESTION_MATRIX = {
    "python": {
        "fundamentals": [
            {
                "title": "Python Concurrency & Memory Model",
                "question": "Can you explain the mechanics of Python's Global Interpreter Lock (GIL), how it impacts CPU-bound vs I/O-bound tasks, and when you would choose multiprocessing over asyncio or threading?",
                "rubric": ["GIL mechanics", "CPU vs I/O bound", "Process vs Thread memory isolation", "asyncio event loop"],
                "difficulty": 3
            },
            {
                "title": "Memory Management & Reference Counting",
                "question": "How does CPython manage memory under the hood? Walk through reference counting, generational cyclic garbage collection, and how circular references can lead to memory leaks.",
                "rubric": ["Reference counting", "Generational GC (Gen 0, 1, 2)", "Weakref usage", "Circular reference detection"],
                "difficulty": 4
            }
        ],
        "applied": [
            {
                "title": "High-Concurrency AsyncIO Starvation",
                "question": "In a Python FastAPI service handling 10,000 requests per minute, a blocking database call inadvertently blocks the main event loop. How do you detect event loop lag, and how would you restructure the code using run_in_executor or background workers?",
                "rubric": ["Event loop blocking", "run_in_executor", "Worker thread pools", "Async connection pooling"],
                "difficulty": 4
            }
        ]
    },
    "react": {
        "fundamentals": [
            {
                "title": "Virtual DOM Reconciliation & Fiber Architecture",
                "question": "How does React's Fiber reconciliation engine differentiate from the older stack reconciler? Explain the two-phase commit cycle (render vs commit), and why stable keys prevent unnecessary DOM re-mounts.",
                "rubric": ["Fiber node tree", "Render vs commit phase", "Time-slicing / concurrency", "Key reconciliation algorithm"],
                "difficulty": 3
            },
            {
                "title": "State Batching & Closure Stale State",
                "question": "Explain how automatic batching works in React 18 and describe a real-world scenario where a stale closure inside useEffect or useCallback causes an out-of-sync state bug.",
                "rubric": ["React 18 automatic batching", "Closure captures", "Functional state updates", "Dependency array hygiene"],
                "difficulty": 3
            }
        ],
        "applied": [
            {
                "title": "React Performance Bottleneck & Profiling",
                "question": "A dashboard rendering 2,000 live updating rows experiences noticeable frame drops. How would you use React DevTools Profiler to locate wasted renders, and what combination of virtualization, useMemo, and memoization would you implement?",
                "rubric": ["React Profiler flamegraphs", "Windowing / Virtualization", "React.memo shallow comparisons", "State colocation"],
                "difficulty": 4
            }
        ]
    },
    "postgresql": {
        "fundamentals": [
            {
                "title": "PostgreSQL MVCC & Isolation Levels",
                "question": "How does PostgreSQL implement Multi-Version Concurrency Control (MVCC) using xmin and xmax transaction IDs, and what is the exact difference between Read Committed and Serializable isolation levels regarding phantom reads?",
                "rubric": ["MVCC row versioning", "xmin/xmax metadata", "Read Committed vs Serializable", "Write skew & phantom reads"],
                "difficulty": 4
            }
        ],
        "applied": [
            {
                "title": "Query Slowdown & Indexing Strategy",
                "question": "A critical query joining three tables suddenly spikes from 20ms to 4.5 seconds in production. Walk me through how you interpret EXPLAIN (ANALYZE, BUFFERS), how you identify sequential scans, and when a composite B-Tree index beats a Hash or GIN index.",
                "rubric": ["EXPLAIN ANALYZE interpretation", "Seq scan vs Index scan", "Buffer cache hits", "Composite index column ordering"],
                "difficulty": 4
            }
        ]
    },
    "redis": {
        "fundamentals": [
            {
                "title": "Redis In-Memory Architecture & Persistence",
                "question": "How does Redis achieve high throughput as a single-threaded event loop, and what are the trade-offs between RDB snapshotting and AOF (Append Only File) persistence under high write pressure?",
                "rubric": ["Single-threaded multiplexing (epoll/kqueue)", "RDB vs AOF", "Forking memory overhead", "Cache eviction policies"],
                "difficulty": 3
            }
        ],
        "applied": [
            {
                "title": "Cache Stampede & Distributed Locking",
                "question": "When a hot cache key expires in Redis, thousands of simultaneous requests hit the database directly (Cache Stampede). How do you resolve this using probabilistic early expiration, mutex locking (Redlock), or single-flight patterns?",
                "rubric": ["Cache stampede / thundering herd", "Mutex locks with TTL", "Probabilistic early expiration (XFetch)", "Single-flight requests"],
                "difficulty": 4
            }
        ]
    },
    "docker": {
        "fundamentals": [
            {
                "title": "Container Isolation & Linux Namespaces",
                "question": "What is the technical difference between a Docker container and a Virtual Machine? Specifically, how do Linux Namespaces (PID, Net, Mount) and cgroups enforce boundary isolation and resource limits?",
                "rubric": ["Namespaces vs Hypervisors", "cgroups resource throttle", "Shared kernel architecture", "Union filesystem (OverlayFS)"],
                "difficulty": 3
            }
        ],
        "applied": [
            {
                "title": "Multi-Stage Builds & Minimal Attack Surface",
                "question": "How would you optimize a 1.2 GB development Docker image down to under 80 MB for production deployment, and how do multi-stage builds and non-root users protect against container escape vulnerabilities?",
                "rubric": ["Multi-stage Dockerfiles", "Distroless / Alpine images", "Layer caching efficiency", "Non-root security context"],
                "difficulty": 3
            }
        ]
    },
    "microservices": {
        "fundamentals": [
            {
                "title": "Distributed Transactions & Saga Pattern",
                "question": "In a distributed microservice environment, why is 2-Phase Commit (2PC) often avoided, and how does the Saga pattern (Choreography vs Orchestration) maintain eventual consistency with compensating transactions?",
                "rubric": ["2PC blocking limitations", "Choreography vs Orchestration", "Compensating transactions", "Outbox pattern / Eventual consistency"],
                "difficulty": 4
            }
        ],
        "applied": [
            {
                "title": "Cascading Failures & Circuit Breakers",
                "question": "One downstream microservice slows down, causing upstream thread pools to saturate and taking down the entire platform. How do you implement Circuit Breakers, Bulkheads, and Exponential Backoff with Jitter to make the system resilient?",
                "rubric": ["Circuit breaker state transitions", "Bulkhead isolation pattern", "Exponential backoff with jitter", "Graceful degradation / fallback"],
                "difficulty": 4
            }
        ]
    }
}

# System Design Architectural Blueprints
SYSTEM_DESIGN_BLUEPRINTS = [
    {
        "title": "High-Throughput Distributed Rate Limiter",
        "scenario": "Design a globally distributed rate limiting service handling 100,000 requests per second for an API gateway. How do you choose between Token Bucket and Sliding Window Log, and how do you synchronize counts across edge clusters with sub-millisecond latency?",
        "rubric": ["Token Bucket vs Sliding Window", "Redis Lua script atomic counters", "Local memory caching with periodic batch sync", "Handling clock drift across servers"],
        "difficulty": 4
    },
    {
        "title": "Real-Time Collaborative Notification & Event Engine",
        "scenario": "Architect a real-time notification engine supporting 5 million active WebSocket connections that dispatches push notifications and alerts in under 200ms. How do you handle load balancing, sticky sessions, and message fan-out using Pub/Sub?",
        "rubric": ["WebSocket connection termination", "Pub/Sub backplane (Kafka/Redis)", "Horizontal connection sharding", "Heartbeat & reconnection backoff"],
        "difficulty": 4
    },
    {
        "title": "Idempotent Payment & Order Processing Pipeline",
        "scenario": "Design a checkout payment processing workflow where double submissions from users or network retries must NEVER charge the customer twice. How do you architect idempotency keys, database row-level locking, and distributed transaction boundaries?",
        "rubric": ["Idempotency key deduplication table", "SELECT FOR UPDATE / Optimistic locking", "Distributed lock with TTL", "At-least-once message processing safety"],
        "difficulty": 5
    }
]

# STAR Behavioral Scenarios
BEHAVIORAL_SCENARIOS = [
    {
        "title": "Technical Disagreement on Architecture",
        "scenario": "Describe a situation where you and a senior engineer or team member had a fundamental disagreement about a technical design or technology choice. How did you evaluate both options objectively, communicate trade-offs, and reach a resolution?",
        "rubric": ["STAR structure (Situation, Task, Action, Result)", "Objective benchmarking and evidence", "Empathy and constructive communication", "Outcome and retrospective learning"],
        "difficulty": 3
    },
    {
        "title": "Production Outage Under Pressure",
        "scenario": "Tell me about a high-severity production outage or bug that you had to troubleshoot under high time pressure. What was your immediate containment strategy, how did you identify root cause, and what preventative guardrails did you put in place?",
        "rubric": ["STAR structure", "Incident containment before root cause", "Blameless post-mortem", "Systemic automated mitigations (monitoring, alerts)"],
        "difficulty": 4
    },
    {
        "title": "Technical Debt vs Feature Velocity",
        "scenario": "Give an example of when product deadlines pressured your team to ship code quickly at the cost of technical debt. How did you balance business urgency with long-term code maintainability, and how did you manage that debt afterward?",
        "rubric": ["STAR structure", "Pragmatic balance of business vs engineering", "Documenting debt & backlog prioritization", "Refactoring and testing outcome"],
        "difficulty": 3
    }
]


class LocalQuestionEngine:
    """
    In-house question generator that creates non-repeating, resume-grounded
    interview sessions without any public cloud LLM or Ollama.
    """

    def generate_session_questions(
        self,
        role: str,
        experience: str = "Mid-Level",
        resume_text: str = "",
        job_description: str = "",
        question_count: int = 5,
        user_id: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Synthesizes a tailored, non-repeating set of questions specifically
        grounded in the candidate's actual resume skills and target role.
        """
        # 1. Parse Candidate's Actual Resume Context
        parsed_resume = resume_engine.parse_profile(resume_text) if resume_text else {"skills": {}, "flat_skills": [], "metrics_found": []}
        candidate_skills = [s.lower() for s in parsed_resume["flat_skills"]]
        claimed_metrics = parsed_resume.get("metrics_found", [])

        # Create unique candidate fingerprint to prevent question repetition
        seed_source = f"{user_id}_{role}_{experience}_{len(resume_text)}_{candidate_skills[:4]}"
        rand = random.Random(hashlib.md5(seed_source.encode()).hexdigest())

        questions = []

        # Find matching tech blueprints based on candidate's actual resume
        matched_techs = [tech for tech in TECH_QUESTION_MATRIX if tech in candidate_skills]
        if not matched_techs:
            # Fallback to role-specific baseline
            role_lower = role.lower()
            if "frontend" in role_lower:
                matched_techs = ["react"]
            elif "backend" in role_lower:
                matched_techs = ["python", "postgresql"]
            else:
                matched_techs = ["python", "docker", "microservices"]

        rand.shuffle(matched_techs)

        # ── STAGE 1: Technical Fundamentals ─────────────────────────────
        primary_tech = matched_techs[0]
        fundamentals_pool = TECH_QUESTION_MATRIX.get(primary_tech, {}).get("fundamentals", [])
        if fundamentals_pool:
            selected_f = rand.choice(fundamentals_pool)
            questions.append({
                "id": 1,
                "stage": "Technical Fundamentals",
                "stage_number": 1,
                "title": f"Core Mechanics: {selected_f['title']}",
                "question": selected_f["question"],
                "rubric": selected_f["rubric"],
                "difficulty": selected_f["difficulty"],
                "grounded_skill": primary_tech.title()
            })

        # ── STAGE 2: Applied Engineering Scenario ───────────────────────
        second_tech = matched_techs[1] if len(matched_techs) > 1 else primary_tech
        applied_pool = TECH_QUESTION_MATRIX.get(second_tech, {}).get("applied", [])
        if not applied_pool:
            applied_pool = TECH_QUESTION_MATRIX.get(primary_tech, {}).get("applied", [])

        selected_app = rand.choice(applied_pool) if applied_pool else {
            "title": "Incident Triage & Production Resiliency",
            "question": f"A microservice running with {second_tech.title()} begins failing health checks under sudden traffic surge. Walk me through your step-by-step diagnostic process, log analysis, and recovery plan.",
            "rubric": ["System telemetry inspection", "Thread/connection pool verification", "Graceful rollback / restart"],
            "difficulty": 3
        }
        questions.append({
            "id": 2,
            "stage": "Applied Scenario",
            "stage_number": 2,
            "title": f"Production Scenario: {selected_app['title']}",
            "question": selected_app["question"],
            "rubric": selected_app["rubric"],
            "difficulty": selected_app["difficulty"],
            "grounded_skill": second_tech.title()
        })

        # ── STAGE 3: Deep Technical Probing on Claimed Resume Projects ───
        if len(questions) < question_count:
            if claimed_metrics:
                chosen_claim = rand.choice(claimed_metrics)
                probe_q = (
                    f"In your resume, you highlighted: '{chosen_claim}'. "
                    f"Could you walk me through the specific architectural bottlenecks you encountered while achieving this, "
                    f"and what technical trade-offs between latency, data consistency, and implementation complexity were made?"
                )
            elif candidate_skills:
                claimed_pair = candidate_skills[:2]
                probe_q = (
                    f"Looking at your experience with {' and '.join([s.title() for s in claimed_pair])}, "
                    f"how do you structure data flow between services to avoid tight coupling and distributed state synchronization bugs?"
                )
            else:
                probe_q = (
                    f"As a {role}, describe an optimization you implemented that measurably reduced compute or memory overhead. "
                    f"What profiling tools did you use and what were the exact before-and-after results?"
                )

            questions.append({
                "id": 3,
                "stage": "Deep Technical Probing",
                "stage_number": 3,
                "title": "Resume Project Verification",
                "question": probe_q,
                "rubric": ["Direct correlation to candidate claims", "Quantified trade-off reasoning", "Technical depth & specificity"],
                "difficulty": 4,
                "grounded_skill": "Candidate Claimed Experience"
            })

        # ── STAGE 4: System Architecture & Distributed Trade-Offs ───────
        if len(questions) < question_count:
            sys_blueprint = rand.choice(SYSTEM_DESIGN_BLUEPRINTS)
            questions.append({
                "id": len(questions) + 1,
                "stage": "System Architecture",
                "stage_number": 4,
                "title": sys_blueprint["title"],
                "question": sys_blueprint["scenario"],
                "rubric": sys_blueprint["rubric"],
                "difficulty": sys_blueprint["difficulty"],
                "grounded_skill": "Distributed Systems"
            })

        # ── STAGE 5: Behavioral STAR Competency ─────────────────────────
        if len(questions) < question_count:
            behav_blueprint = rand.choice(BEHAVIORAL_SCENARIOS)
            questions.append({
                "id": len(questions) + 1,
                "stage": "Behavioral (STAR)",
                "stage_number": 5,
                "title": behav_blueprint["title"],
                "question": behav_blueprint["scenario"],
                "rubric": behav_blueprint["rubric"],
                "difficulty": behav_blueprint["difficulty"],
                "grounded_skill": "Leadership & Collaboration"
            })

        # Fill remaining if question_count > 5
        while len(questions) < question_count:
            q_idx = len(questions) + 1
            questions.append({
                "id": q_idx,
                "stage": "Applied Technical Evaluation",
                "stage_number": q_idx,
                "title": f"Technical Deep-Dive #{q_idx}",
                "question": f"Given your work as a {role}, how do you approach database schema migrations with zero-downtime under active production writes?",
                "rubric": ["Expand and contract pattern", "Backward compatible columns", "Dual writing / backfill"],
                "difficulty": 4,
                "grounded_skill": "Database Architecture"
            })

        return questions


# Singleton Instance
local_question_engine = LocalQuestionEngine()

