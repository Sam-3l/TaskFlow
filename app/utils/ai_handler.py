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

def clean_json_code_block(raw_text: str) -> str:
    """
    Cleans markdown-style code block formatting from AI responses like:
    ```json
    { ... }
    ```
    """
    if raw_text.strip().startswith("```"):
        blocks = raw_text.strip().split('```')
        for block in blocks:
            block = block.strip()
            if block.startswith("json"):
                block = block[4:].strip()  # Remove 'json' prefix
            if block.startswith('{') and block.endswith('}'):
                return block
    return raw_text.strip()

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

def generate_task_priority_analysis(tasks):
    """
    Use Gemini to analyze and sort tasks based on priority, deadlines, and descriptions.
    Returns a JSON with task execution order and a smart summary.
    """

    tasks_text = "\n".join(
        f"- ID: {task.id} | Title: {task.title} | Priority: {task.priority} | "
        f"Deadline: {task.deadline.strftime('%Y-%m-%d') if task.deadline else 'None'} | "
        f"Description: {task.description[:100] if task.description else 'None'}"
        for task in tasks
    )

    prompt = f"""
    You are an expert productivity consultant helping users optimize their workflow.

    Analyze the following list of tasks and return them in the BEST EXECUTION ORDER based on:
    - Priority (High, Medium, Low)
    - Deadline urgency
    - Task complexity inferred from the description

    Return STRICTLY in JSON format with:
    - "task_order": an array of task IDs sorted from most urgent/important to least (e.g., [3, 1, 4, 2])
    - "summary": a SINGLE impressive sentence summarizing your reasoning (e.g., "Start with Task 3 <don't refer to the ID though> since it's high priority with an urgent deadline, then...")

    Do NOT include any extra text, notes, or formatting outside the JSON.

    Tasks:
    {tasks_text}
    """

    result = query_gemini(prompt)

    if not result['success']:
        raise ValueError(f"AI generation failed: {result['error']}")

    content = clean_json_code_block(result['response'].strip())

    try:
        response_data = json.loads(content)

        if not (
            isinstance(response_data.get("task_order"), list)
            and isinstance(response_data.get("summary"), str)
        ):
            raise ValueError("Invalid response format from AI")

        return response_data

    except json.JSONDecodeError as e:
        print(f"JSON parsing error: {e}")
        print(f"Raw AI response: {content}")
        raise ValueError("Could not parse AI response into JSON format")

def generate_task_insight(task):
    """
    Generates AI-powered task insights including:
    - Estimated time
    - Urgency
    - Next step
    - Risks/blockers
    - Smart suggestion
    """

    # Prepare the input for the AI
    task_text = (
        f"Title: {task.title}\n"
        f"Description: {task.description or 'None'}\n"
        f"Priority: {task.priority}\n"
        f"Deadline: {task.deadline.strftime('%Y-%m-%d') if task.deadline else 'None'}\n"
        f"Status: {task.status}\n"
        f"Subtasks:\n"
    )

    # Add subtasks if available
    if hasattr(task, 'todos') and task.todos:
        for todo in task.todos:
            status = 'completed' if todo.is_completed else 'incomplete'
            task_text += f"- {todo.content} ({status})\n"
    else:
        task_text += "- None\n"

    # AI Prompt
    prompt = f"""
    You are an expert productivity consultant.

    Given the task details below, analyze and return ONLY the following insights in STRICT JSON format:
    - "estimated_time": Estimated time to complete (e.g., "2-3 hours")
    - "urgency": High, Medium, or Low (based on priority, deadline, and todo progress)
    - "next_step": The most logical immediate action the user should take
    - "risks": List of potential risks or blockers (e.g., tight deadline, many incomplete subtasks, missing info)
    - "suggestion": A smart tip or advice to help complete the task more efficiently

    Do NOT include any other text or explanation outside the JSON.

    Example format:
    {{
    "estimated_time": "...",
    "urgency": "...",
    "next_step": "...",
    "risks": [...],
    "suggestion": "..."
    }}

    Task Details:
    {task_text}
    """

    # Query Gemini
    result = query_gemini(prompt)

    if not result["success"]:
        raise ValueError(f"AI generation failed: {result['error']}")

    content = clean_json_code_block(result["response"].strip())

    # Parse the JSON response
    try:
        response_data = json.loads(content)

        # Validate expected fields
        expected_keys = {"estimated_time", "urgency", "next_step", "risks", "suggestion"}
        if not expected_keys.issubset(response_data.keys()):
            raise ValueError(f"Missing expected keys in AI response: {response_data}")

        if not isinstance(response_data["risks"], list):
            raise ValueError("Risks should be a list")

        return response_data

    except (json.JSONDecodeError, ValueError) as e:
        print(f"AI Parsing Error: {e}")
        print(f"Raw AI Response: {content}")
        raise ValueError("Could not parse AI response into JSON format")