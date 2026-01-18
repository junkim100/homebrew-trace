"""
Chat module for Trace

Provides the chat API endpoint and answer synthesis for
time-aware conversations about the user's digital activity.
"""

from src.chat.api import ChatAPI, ChatRequest, ChatResponse

__all__ = [
    "ChatAPI",
    "ChatRequest",
    "ChatResponse",
]
