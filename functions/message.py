from dataclasses import dataclass, asdict
from typing import Dict, List, Any, Optional
from enum import StrEnum


class Persona(StrEnum):
    user = "user"
    chat = "chat"
    grammar = "grammar"
    vocab = "vocab"
    politeness = "politeness"
    context = "context"

@dataclass(frozen=True)
class Message:
    persona: Persona
    content: str

    @staticmethod
    def from_dict(d: Dict[str, Any]):
        return Message(
            persona=Persona(d["persona"]),
            content=d["content"],
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def to_openai(self) -> Dict[str, Any] | None:
        if self.persona == Persona.user:
            return {
                "role": "user",
                "content": self.content,
            }
        elif self.persona == Persona.chat:
            return {
                "role": "assistant",
                "content": self.content,
            }
        else:
            return None