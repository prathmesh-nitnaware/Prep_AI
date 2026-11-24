#!/usr/bin/env python
"""Test script for LocalQuestionEngine"""
import sys, os
sys.path.append('D:/Prep_AI')
from backend.services.ai.local_question_engine import LocalQuestionEngine

sample_resume = """John Doe
Software Engineer with 5 years experience in Python, Flask, Docker, PostgreSQL.
Implemented a microservice handling 10k rps, reduced latency by 30%.
"""

engine = LocalQuestionEngine()
questions = engine.generate_session_questions(
    role="Backend Engineer",
    experience="Mid-Level",
    resume_text=sample_resume,
    job_description="We need a backend engineer proficient in Python and PostgreSQL.",
    question_count=5,
    user_id="test_user_1"
)
import pprint
pprint.pprint(questions)
