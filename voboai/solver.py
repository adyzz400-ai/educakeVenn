import google.generativeai as genai
import json

from config import GEMINI_API_KEY


if GEMINI_API_KEY:
    genai.configure(
        api_key=GEMINI_API_KEY
    )


def solve_question(question):
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured."
        )

    model = genai.GenerativeModel(
        "gemini-2.0-flash"
    )

    prompt = f"""
You are helping solve a school homework question.

Return ONLY valid JSON:

{{
  "answer": "short answer",
  "explanation": "short explanation"
}}

Question:

{question}
"""

    response = model.generate_content(
        prompt
    )

    text = response.text.strip()

    if text.startswith("```"):
        text = (
            text.replace("```json", "")
            .replace("```", "")
            .strip()
        )

    try:
        data = json.loads(text)

        return {
            "answer": str(
                data.get("answer", "")
            ),
            "explanation": str(
                data.get("explanation", "")
            ),
        }

    except Exception:
        return {
            "answer": text,
            "explanation": "",
        }
