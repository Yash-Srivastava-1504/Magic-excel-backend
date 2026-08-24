import json
import os
import re

LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "llm_logs.json")

def _log_llm_interaction(input_data, response_content, agent_name="Unknown Agent"):
    # Simplify input
    final_input = input_data
    if isinstance(input_data, list) and all(isinstance(m, dict) for m in input_data):
        user_msgs = [m.get("content") for m in input_data if m.get("role") == "user"]
        final_input = "\n".join(user_msgs) if user_msgs else input_data

    # Simplify output if it's json
    final_output = response_content
    if isinstance(response_content, str):
        try:
            final_output = json.loads(response_content)
        except Exception:
            pass

    log_entry = {
        "name": agent_name,
        "input": final_input,
        "output": final_output
    }
    
    logs = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
                if not isinstance(logs, list):
                    logs = []
        except Exception:
            logs = []
            
    logs.append(log_entry)
    
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2)
    except Exception as e:
        print(f"Failed to log LLM interaction: {e}")
from typing import List, Dict, Any, Optional, TypeVar, Type
from pydantic import BaseModel, ValidationError
from openai import AsyncOpenAI
from app.config import settings

T = TypeVar("T")

FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"

def _is_ollama() -> bool:
    return bool(settings.OLLAMA_BASE_URL)

def _get_model() -> str:
    return settings.DEFAULT_MODEL if _is_ollama() else settings.FIREWORKS_MODEL

def build_client() -> AsyncOpenAI:
    if _is_ollama():
        return AsyncOpenAI(base_url=settings.OLLAMA_BASE_URL, api_key="ollama")
    return AsyncOpenAI(
        base_url=FIREWORKS_BASE_URL,
        api_key=settings.FIRE_WORKS_API or "",
    )

async def chat_completion(messages: List[Dict[str, str]], agent_name: str = "Unknown Agent") -> str:
    provider = "Ollama" if _is_ollama() else "Fireworks"
    print(f"[{provider}] Running agent: {agent_name}")
    client = build_client()
    kwargs: Dict[str, Any] = dict(
        model=_get_model(),
        messages=messages,
        temperature=0.7,
        max_tokens=4096,
    )
    if not _is_ollama():
        kwargs.update(temperature=0.6, max_tokens=4096, top_p=1,
                      presence_penalty=0, frequency_penalty=0,
                      extra_body={"top_k": 40})
    try:
        response = await client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or ""
        
        _log_llm_interaction(messages, content, agent_name)
        
        # Clean up potential markdown formatting
        if content.startswith("```json"):
            content = content.replace("```json", "").replace("```", "").strip()
        elif content.startswith("```"):
            content = content.replace("```", "").strip()
        
        return content
    except Exception as e:
        print(f"LLM API Error: {str(e)}")
        return ""

async def chat_completion_model(
    system_prompt: str,
    user_message: str,
    response_model: Type[T],
    fallback: T,
    agent_name: str = "Unknown Agent",
) -> T:
    provider = "Ollama" if _is_ollama() else "Fireworks"
    print(f"[{provider}] Running agent: {agent_name}")
    client = build_client()
    kwargs: Dict[str, Any] = dict(
        model=_get_model(),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=0.7,
        max_tokens=2048,
        response_format={"type": "json_object"},
    )
    if not _is_ollama():
        kwargs.update(temperature=0.6, max_tokens=4096, top_p=1,
                      presence_penalty=0, frequency_penalty=0,
                      extra_body={"top_k": 40})
    try:
        response = await client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or ""
        
        log_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        _log_llm_interaction(log_messages, content, agent_name)
        
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```[a-z]*\n?", "", content)
            content = re.sub(r"\n?```$", "", content)
            content = content.strip()
        data = json.loads(content)
        return response_model.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as e:
        print(f"LLM model parse/validation error: {e}")
        return fallback
    except Exception as e:
        print(f"LLM API error: {e}")
        return fallback

async def chat_completion_json(system_prompt: str, user_message: str, fallback: T, agent_name: str = "Unknown Agent") -> T:
    content = await chat_completion([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ], agent_name=agent_name)
    
    if not content:
        return fallback
    
    try:
        return json.loads(content)
    except Exception as e:
        print(f"LLM Parse Error: {str(e)}\nRaw Content: {content}")
        return fallback
