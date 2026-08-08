"""Load the chat model for the agent (Groq's free-tier hosted models)."""

from __future__ import annotations

import os

from langchain_groq import ChatGroq

DEFAULT_MODEL = "llama-3.3-70b-versatile"


def load_llm(api_key: str | None = None, model: str = DEFAULT_MODEL) -> ChatGroq:
    """Return a configured ChatGroq client.

    The API key is taken from the argument if given, otherwise from the
    GROQ_API_KEY environment variable. It is never hard-coded here.
    """
    key = api_key or os.environ.get("GROQ_API_KEY")
    if not key:
        raise ValueError(
            "No Groq API key found. Pass api_key=... or set GROQ_API_KEY."
        )
    return ChatGroq(api_key=key, model=model, temperature=0)