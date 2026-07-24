"""
Calls the Groq API to generate a single SSC CGL question for a given topic,
validates the response, and checks it against the existing question bank
to avoid duplicates. Retries on duplicate/invalid output.
"""

import json
import os
import random
import string
import requests

import config
import database as db

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

PROMPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")

SYSTEM_INSTRUCTIONS = """You are an expert SBI PO / SSC CGL English exam question setter.
Respond with ONLY a single valid JSON object, no markdown fences, no commentary, no preamble.

The JSON object must have exactly this shape:
{
  "focus_word": "<the single core word/idiom/phrase this question centers on>",
  "question": "<the FULL question text -- see completeness rule below>",
  "options": ["<option A>", "<option B>", "<option C>", "<option D>"],
  "correct_index": <integer 0-3, index into options of the single correct answer>,
  "explanation": "<ONE crisp sentence, see format below>"
}

CRITICAL COMPLETENESS RULE (this fixes a real bug where questions came out
missing the actual word/blank):
- If this question is about a specific word (synonym/antonym/spelling/idiom/
  one-word-substitution/error-spotting target), the question text MUST
  explicitly contain that exact word or phrase written out in full. NEVER
  write something like "choose the word with the same meaning" without
  actually including the word itself in the question text.
- If this question involves a blank, the question text MUST contain the
  blank marker "____" (four underscores) at the correct position. Never
  omit the blank marker.
- Before finalizing, re-read your own "question" field and confirm a reader
  seeing ONLY that field (no other context) has everything needed to answer
  it. If anything referenced is missing from the text, fix it.

Other rules:
- Exactly 4 options, only one correct.
- Match real SBI PO / SSC CGL difficulty -- not GRE/CAT/IELTS level.
- The question must be self-contained and answerable from its own text alone.
- "explanation": exactly ONE short sentence (under 140 characters), plain
  language, stating why the correct option is right. No bullet points, no
  breakdown of the other options, no line breaks. Telegram shows this inline
  right under the poll, so it must be short enough to read in one glance.
- Output must be valid JSON parseable by a strict JSON parser. No trailing commas.
- Never truncate or cut off the "question", "options", or "explanation" fields
  partway through a word or sentence -- always finish every field completely.
"""


def _load_topic_prompt(topic):
    path = os.path.join(PROMPT_DIR, f"{topic}.txt")
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def _call_groq(topic_instruction, avoid_words=None, letter_hint=None):
    headers = {
        "Authorization": f"Bearer {config.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    user_content = topic_instruction
    if avoid_words:
        word_list = ", ".join(avoid_words)
        user_content += (
            "\n\nIMPORTANT: Do NOT use any of the following words/phrases as the focus_word "
            "-- they have already been used and must never repeat:\n"
            f"{word_list}"
        )
    if letter_hint:
        user_content += (
            f"\n\nTry to pick a focus_word that starts with the letter '{letter_hint}' "
            "if a natural, exam-appropriate word starting with that letter fits this "
            "topic. If nothing suitable starts with that letter, pick any other fresh word "
            "instead -- just don't default to the most common/obvious word for this topic."
        )

    payload = {
        "model": config.GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.9,
        "max_tokens": config.GROQ_MAX_TOKENS,
    }
    resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=config.GROQ_TIMEOUT_SECONDS)
    resp.raise_for_status()
    data = resp.json()

    choice = data["choices"][0]
    finish_reason = choice.get("finish_reason")
    content = choice["message"]["content"].strip()

    if finish_reason == "length":
        # The model ran out of tokens mid-generation -- the JSON is guaranteed
        # incomplete. Raise explicitly instead of letting json.loads produce a
        # confusing generic parse error, so the retry loop logs the real cause.
        raise TruncatedGenerationError(f"Groq cut the response short (finish_reason=length)")

    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:].strip()

    return json.loads(content)


class TruncatedGenerationError(Exception):
    pass


BLANK_STYLE_TOPICS = {
    "cloze_test", "fill_in_the_blanks", "vocabulary", "sentence_improvement",
    "phrase_replacement", "reading_comprehension",
}
WORD_MUST_APPEAR_TOPICS = {
    "synonyms", "antonyms", "spelling", "idioms", "one_word_substitution",
    "homonyms", "pronunciation", "error_spotting",
}


def _validate(payload, topic):
    if not isinstance(payload, dict):
        return False, "not a dict"
    required = {"focus_word", "question", "options", "correct_index", "explanation"}
    if not required.issubset(payload.keys()):
        return False, "missing required keys"
    if not isinstance(payload["options"], list) or len(payload["options"]) != 4:
        return False, "options must be a list of 4"
    if any(not str(o).strip() for o in payload["options"]):
        return False, "an option is empty"
    if not isinstance(payload["correct_index"], int) or not (0 <= payload["correct_index"] <= 3):
        return False, "correct_index out of range"
    question = str(payload["question"]).strip()
    if not question:
        return False, "empty question"
    focus_word = str(payload["focus_word"]).strip()
    if not focus_word:
        return False, "empty focus_word"
    if not str(payload["explanation"]).strip():
        return False, "empty explanation"

    # Completeness check -- this is what catches the "word/blank omitted" bug.
    if topic in WORD_MUST_APPEAR_TOPICS:
        if focus_word.lower() not in question.lower():
            return False, f"focus_word '{focus_word}' does not appear in question text"
    if topic in BLANK_STYLE_TOPICS:
        if "___" not in question:
            return False, "blank marker '____' missing from question text"

    return True, None


def generate_unique_question(topic):
    """
    Generate a question for `topic`. The hard guarantee against repeats comes
    from database.record_used_word() (a UNIQUE-constrained table covering your
    ENTIRE history, not a recent window) -- so even if the LLM ignores the
    "don't reuse this word" instruction, a repeat can never actually be saved.

    Each retry also nudges the model toward a different, randomly-chosen
    starting letter, which in practice does a lot to stop it circling back to
    the same "obvious" word for a topic.

    Returns (question_id, focus_word), or (None, None) if all retries were exhausted.
    """
    topic_instruction = _load_topic_prompt(topic)

    for attempt in range(config.MAX_GENERATION_RETRIES):
        avoid_sample = db.get_used_words_sample(limit=30)
        letter_hint = random.choice(string.ascii_uppercase)

        try:
            payload = _call_groq(topic_instruction, avoid_words=avoid_sample, letter_hint=letter_hint)
        except TruncatedGenerationError as e:
            print(f"[{topic}] attempt {attempt + 1}: {e} -- retrying")
            continue
        except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
            print(f"[{topic}] generation attempt {attempt + 1} failed: {e}")
            continue

        ok, reason = _validate(payload, topic)
        if not ok:
            print(f"[{topic}] attempt {attempt + 1}: invalid ({reason}), retrying")
            continue

        focus_word = str(payload["focus_word"]).strip()

        # Hard gate: check against the FULL permanent history, not a recent window.
        if db.is_word_used(focus_word):
            print(f"[{topic}] attempt {attempt + 1}: '{focus_word}' already used (ever), retrying")
            continue

        if db.question_exists(payload["question"]):
            print(f"[{topic}] attempt {attempt + 1}: duplicate question text, retrying")
            continue

        # Atomically claim the word FIRST. If this fails, something else beat us
        # to it (shouldn't happen in this single-threaded flow, but it's the
        # actual source of truth -- belt and suspenders).
        if not db.record_used_word(focus_word, topic):
            print(f"[{topic}] attempt {attempt + 1}: '{focus_word}' lost the race, retrying")
            continue

        qid = db.save_question(
            topic=topic,
            question_text=payload["question"],
            options=payload["options"],
            correct_index=payload["correct_index"],
            explanation=payload["explanation"],
            focus_word=focus_word,
        )
        return qid, focus_word

    print(f"[{topic}] exhausted {config.MAX_GENERATION_RETRIES} retries without a fresh word")
    return None, None