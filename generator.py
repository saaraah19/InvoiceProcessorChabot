"""
generator.py — Generic Gemini client. --- Talks to GEMINI
Knows nothing about invoices. Accepts any contents + schema, returns a parsed Pydantic object.
"""


import os
import re
import time
import logging
from google import genai
from google.genai import types
from dotenv import load_dotenv
from config import GEMINI_MODEL_NAME, MAX_RETRIES
load_dotenv()
logger = logging.getLogger(__name__)

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

def call_gemini(contents: list, response_schema) -> object:
    """
    Send contents to Gemini with a structured response schema.
    Retries on 429 (rate limit) and 503 (server overload).
    Returns a parsed Pydantic object on success, raises RuntimeError after max retries.
    """
    config = types.GenerateContentConfig(
        temperature=0.0,
        response_mime_type="application/json",
        response_schema=response_schema,
    )

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL_NAME,
                contents=contents,
                config=config,
            )
            return response.parsed  # ← the link to your Pydantic class

        except Exception as e:
            error_str = str(e)

            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                match = re.search(r'retry in (\d+)s', error_str)
                wait = int(match.group(1)) + 3 if match else 15
                logger.warning(f"Rate limited — waiting {wait}s (attempt {attempt}/{MAX_RETRIES})")
                time.sleep(wait)

            elif "503" in error_str or "UNAVAILABLE" in error_str:
                logger.warning(f"Service unavailable — waiting 10s (attempt {attempt}/{MAX_RETRIES})")
                time.sleep(10)

            else:
                raise  # anything else (auth error, bad request) → fail immediately, don't retry

    raise RuntimeError(f"Gemini call failed after {MAX_RETRIES} attempts")
