import os
import re
import time
import logging
from typing import TypeVar, Type
from google import genai
from google.genai import types
from dotenv import load_dotenv
from config import GEMINI_MODEL_NAME, MAX_RETRIES

load_dotenv()
logger = logging.getLogger(__name__)

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# Define a type variable that can represent any Pydantic model class
T = TypeVar('T')

def call_gemini(contents: list, response_schema: Type[T]) -> T:
    """
    Send contents to Gemini with a structured response schema.
    Retries on 429 (rate limit) and 503 (server overload).
    Returns a parsed Pydantic object of type `response_schema` on success,
    raises RuntimeError after max retries.
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
            # response.parsed is an instance of response_schema (T)
            return response.parsed  # type: ignore  # noqa

        except Exception as e:
            error_str = str(e)

            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                match = re.search(r'retry in (\d+)s', error_str)
                wait = min(5 * (2 ** (attempt - 1)), 60)  # 5, 10, 20, 40, 60, 60 seconds
                logger.warning(f"Rate limited — waiting {wait}s (attempt {attempt}/{MAX_RETRIES})")
                time.sleep(wait)

            elif "503" in error_str or "UNAVAILABLE" in error_str:
                wait = min(5 * (2 ** (attempt - 1)), 60)  # 5, 10, 20, 40, 60, 60 seconds
                logger.warning(f"Rate limited — waiting {wait}s (attempt {attempt}/{MAX_RETRIES})")
                time.sleep(wait)


            else:
                raise

    raise RuntimeError(f"Gemini call failed after {MAX_RETRIES} attempts")