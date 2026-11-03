from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: str = Field(..., min_length=1)
    content: str = Field(...)
    timestamp: Optional[str] = Field(default=None)

    @model_validator(mode="before")
    @classmethod
    def _coerce_content(cls, data: Any) -> Any:
        """Turn a missing or None message content into a string."""
        if isinstance(data, dict) and "content" in data:
            data["content"] = "" if data["content"] is None else str(data["content"])
        return data

    def as_openrouter(self) -> Dict[str, str]:
        """Return the message as an OpenRouter role/content dict."""
        return {"role": self.role.strip(), "content": self.content}


class ChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    messages: List[ChatMessage] = Field(default_factory=list)
    model: Optional[str] = None
    system: Optional[str] = None
    stream: bool = True

    def openrouter_messages(self) -> List[Dict[str, str]]:
        """Return the non-empty messages in OpenRouter format."""
        return [msg.as_openrouter() for msg in self.messages if msg.content.strip()]


class ChatHistoryResponse(BaseModel):
    messages: List[ChatMessage] = Field(default_factory=list)


class ChatHistoryClearResponse(BaseModel):
    ok: bool = True
