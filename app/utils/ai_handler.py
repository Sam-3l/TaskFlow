import os
import re
import json
import logging

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, GoogleAPIError

# Configure Gemini API Key
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Models priority list (best first)
MODEL_PRIORITY = [
    'gemini-1.5-flash',
    'gemini-1.5-flash-lite'
]


def query_gemini(prompt: str, system_instruction: str = None) -> dict:
    """
    Sends a prompt to Gemini with fallback handling.

    Args:
        prompt (str): The user prompt.
        system_instruction (str, optional): Optional system-level instruction to guide responses.

    Returns:
        dict: {'success': True, 'response': str} OR {'success': False, 'error': str}
    """
    for model_name in MODEL_PRIORITY:
        try:
            logging.info(f"Trying Gemini model: {model_name}")

            # Load model
            model = genai.GenerativeModel(model_name)

            # Send prompt
            chat = model.start_chat(history=[])

            parts = [prompt]
            if system_instruction:
                parts.insert(0, system_instruction)

            response = chat.send_message(parts)

            return {
                'success': True,
                'model': model_name,
                'response': response.text
            }

        except ResourceExhausted as e:
            logging.warning(f"Quota or rate limit exceeded for {model_name}: {e}")
            continue  # Try next fallback model

        except GoogleAPIError as e:
            logging.error(f"API error for {model_name}: {e}")
            continue  # Try next fallback model

        except Exception as e:
            logging.error(f"Unexpected error for {model_name}: {e}")
            continue

    # All attempts failed
    return {
        'success': False,
        'error': "AI assistant is temporarily busy or unavailable. Please try again in a little while."
    }


def generate_ai_subtasks(task):
    """
    Generate subtasks for a task using Gemini API with robust JSON parsing.
    """

    prompt = f"""
    You are a helpful productivity assistant that breaks down tasks into specific, actionable subtasks.
    Based on the following task details, suggest 3 to 7 specific subtasks (todos) that would help complete this task.

    Return ONLY a JSON array formatted EXACTLY like:
    ["First subtask", "Second subtask", "Third subtask"]

    Do NOT include any explanations, introductions, or extra text.

    Task Title: {task.title}
    Description: {task.description or "None"}
    Priority: {task.priority}
    Deadline: {task.deadline.strftime('%Y-%m-%d') if task.deadline else "None"}
    """

    result = query_gemini(prompt)

    if not result['success']:
        raise ValueError(f"AI generation failed: {result['error']}")

    content = result['response'].strip()

    try:
        # Direct JSON parsing attempt
        subtasks = json.loads(content)

        if not isinstance(subtasks, list):
            raise ValueError("Response was not a JSON array")

        return [s.strip() for s in subtasks if isinstance(s, str) and s.strip()]

    except json.JSONDecodeError:
        # Fallback: Extract array-like patterns from raw string
        try:
            json_str = content.split('[', 1)[-1]
            json_str = '[' + json_str.split(']', 1)[0] + ']'
            subtasks = json.loads(json_str)

            if not isinstance(subtasks, list):
                raise ValueError("Fallback response was not a JSON array")

            return [s.strip() for s in subtasks if isinstance(s, str) and s.strip()]

        except Exception:
            # Last fallback: Regex quoted strings
            matches = re.findall(r'"(.*?)"', content)
            if matches:
                return matches[:7]  # Max 7 subtasks

            raise ValueError("Could not parse subtasks from AI response")
