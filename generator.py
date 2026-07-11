"""
Calls the Groq API to generate a single SSC CGL question for a given topic,
validates the response, and checks it against the existing question bank
to avoid duplicates. Retries on duplicate/invalid output.
"""

import json
import os
import requests

import config
import database as db

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

PROMPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")

SYSTEM_INSTRUCTIONS = """You are an expert SSC CGL Tier-I English exam question setter.
Respond with ONLY a single valid JSON object, no markdown fences, no commentary, no preamble.

The JSON object must have exactly this shape:
{
  "focus_word": "<the single core word, idiom, or phrase this question is built around>",
  "question": "<the question text>",
  "options": ["<option A>", "<option B>", "<option C>", "<option D>"],
  "correct_index": <integer 0-3, index into options of the single correct answer>,
  "explanation": "<formatted with newlines and bullets, see format below>"
}

Rules:
- Exactly 4 options, only one correct.
- Match real SSC CGL Tier-I difficulty and style -- not GRE/CAT/IELTS level.
- The question must be self-contained and unambiguous without needing audio or images.

FORMAT FOR "explanation" (this is a JSON string, so use \\n for line breaks):
- Line 1: one short sentence starting with "✅ Correct:" naming the right option and why,
  in plain simple words. One sentence, not a paragraph.
- Then one short bullet per OTHER option (3 bullets total), each starting with "• ",
  giving just that word/option's meaning in 5-8 words. No long sentences.
- No extra commentary, no restating the question, no filler like "let's see" or "in conclusion".
- Every line should be short enough to read at a glance on a phone screen.

Example shape (word choice is just illustrative, always use fresh content):
"✅ Correct: Hardworking — diligent means showing care and effort in work.\\n• Lazy — unwilling to work or make an effort\\n• Rude — impolite or disrespectful in manner\\n• Slow — not quick; taking a long time"

- Output must be valid JSON parseable by a strict JSON parser. No trailing commas.
"""


def _load_topic_prompt(topic):
    path = os.path.join(PROMPT_DIR, f"{topic}.txt")
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def _call_groq(topic_instruction, avoid_words=None):
    headers = {
        "Authorization": f"Bearer {config.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    user_content = topic_instruction
    if avoid_words:
        word_list = ", ".join(avoid_words)
        user_content += (
            "\n\nIMPORTANT: Do NOT use any of the following words/phrases as the focus_word "
            "for this question -- they have already been used recently and must not repeat:\n"
            f"{word_list}"
        )

    payload = {
        "model": config.GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.9,
        "max_tokens": 600,
    }
    resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"].strip()

    # Strip accidental markdown fences if the model adds them anyway.
    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:].strip()

    return json.loads(content)


def _validate(payload):
    if not isinstance(payload, dict):
        return False
    required = {"focus_word", "question", "options", "correct_index", "explanation"}
    if not required.issubset(payload.keys()):
        return False
    if not isinstance(payload["options"], list) or len(payload["options"]) != 4:
        return False
    if not isinstance(payload["correct_index"], int) or not (0 <= payload["correct_index"] <= 3):
        return False
    if not payload["question"].strip():
        return False
    if not str(payload["focus_word"]).strip():
        return False
    return True


def generate_unique_question(topic, avoid_words=None):
    """
    Generate a question for `topic`, retrying on duplicates/invalid output/
    reused focus words. `avoid_words` is a list of recently-used focus words
    (across all topics) that must not be reused, so a single session doesn't
    end up testing the same word four different ways.

    Returns (question_id, focus_word), or (None, None) if all retries were exhausted.
    """
    topic_instruction = _load_topic_prompt(topic)
    avoid_words = avoid_words or []

    for attempt in range(config.MAX_GENERATION_RETRIES):
        try:
            payload = _call_groq(topic_instruction, avoid_words=avoid_words)
        except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
            print(f"[{topic}] generation attempt {attempt + 1} failed: {e}")
            continue

        if not _validate(payload):
            print(f"[{topic}] attempt {attempt + 1}: invalid schema, retrying")
            continue

        focus_word = str(payload["focus_word"]).strip().lower()

        if focus_word in [w.lower() for w in avoid_words]:
            print(f"[{topic}] attempt {attempt + 1}: focus_word '{focus_word}' already used, retrying")
            continue

        if db.question_exists(payload["question"]):
            print(f"[{topic}] attempt {attempt + 1}: duplicate question, retrying")
            continue

        qid = db.save_question(
            topic=topic,
            question_text=payload["question"],
            options=payload["options"],
            correct_index=payload["correct_index"],
            explanation=payload["explanation"],
            focus_word=payload["focus_word"].strip(),
        )
        return qid, payload["focus_word"].strip()

    print(f"[{topic}] exhausted {config.MAX_GENERATION_RETRIES} retries without success")
    return None, None