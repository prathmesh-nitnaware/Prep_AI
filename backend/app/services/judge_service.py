import os
import requests
import time
import base64
import logging

logger = logging.getLogger(__name__)


class JudgeService:
    """
    Submits code to Judge0 for secure execution via RapidAPI.
    Fails closed when API credentials are absent or unconfigured.
    """
    JUDGE0_URL = "https://judge0-ce.p.rapidapi.com"

    LANGUAGE_IDS = {
        "python": 71,
        "javascript": 63,
        "java": 62,
        "cpp": 54
    }

    @classmethod
    def get_api_key(cls) -> str:
        """
        Dynamically resolves the RapidAPI/Judge0 key from environment variables.
        Checks RAPIDAPI_KEY first, falling back to JUDGE0_API_KEY.
        Strips and validates each environment variable independently.
        Treats missing, empty, whitespace-only, and placeholder keys as unconfigured.
        """
        rapidapi_raw = os.getenv("RAPIDAPI_KEY")
        if rapidapi_raw is not None:
            rapidapi_key = rapidapi_raw.strip()
            if rapidapi_key and rapidapi_key != "REPLACE_WITH_YOUR_KEY":
                return rapidapi_key

        judge0_raw = os.getenv("JUDGE0_API_KEY")
        if judge0_raw is not None:
            judge0_key = judge0_raw.strip()
            if judge0_key and judge0_key != "REPLACE_WITH_YOUR_KEY":
                return judge0_key

        return ""

    @classmethod
    def execute(cls, code: str, language: str = "python", stdin: str = ""):
        """
        Submits code for remote execution. Fails closed if credentials are not configured.
        """
        api_key = cls.get_api_key()
        if not api_key:
            logger.warning("Judge0 code execution key is not configured; execution request failed closed")
            return {"error": "Code execution engine is not configured."}

        payload = {
            "source_code": base64.b64encode(code.encode()).decode(),
            "language_id": cls.LANGUAGE_IDS.get(language, 71),
            "stdin": base64.b64encode(stdin.encode()).decode()
        }
        
        headers = {
            "content-type": "application/json",
            "X-RapidAPI-Key": api_key,
            "X-RapidAPI-Host": "judge0-ce.p.rapidapi.com"
        }

        # Submit
        response = requests.post(f"{cls.JUDGE0_URL}/submissions?base64_encoded=true&wait=true", 
                                 json=payload, headers=headers)
        
        if response.status_code == 201:
            result = response.json()
            return {
                "stdout": base64.b64decode(result.get("stdout", "")).decode() if result.get("stdout") else "",
                "stderr": base64.b64decode(result.get("stderr", "")).decode() if result.get("stderr") else "",
                "compile_output": base64.b64decode(result.get("compile_output", "")).decode() if result.get("compile_output") else "",
                "time": result.get("time"),
                "memory": result.get("memory"),
                "status": result.get("status", {}).get("description")
            }
        
        return {"error": "Submission failed"}
