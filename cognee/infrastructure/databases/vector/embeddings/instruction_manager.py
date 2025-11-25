"""Utilities for instruction-aware embedding workflows."""

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterable, List, Literal, Optional

from cognee.infrastructure.databases.vector.embeddings.config import (
    get_embedding_config,
)

InstructionRole = Literal["query", "passage"]

INSTRUCTION_CONFIG = {
    "nl2code": {
        "query": "Find the most relevant code snippet given the following query:\n",
        "passage": "Candidate code snippet:\n",
    },
    "qa": {
        "query": "Find the most relevant answer given the following question:\n",
        "passage": "Candidate answer:\n",
    },
    "code2code": {
        "query": "Find an equivalent code snippet given the following code snippet:\n",
        "passage": "Candidate code snippet:\n",
    },
    "code2nl": {
        "query": "Find the most relevant comment given the following code snippet:\n",
        "passage": "Candidate comment:\n",
    },
    "code2completion": {
        "query": "Find the most relevant completion given the following start of code snippet:\n",
        "passage": "Candidate completion:\n",
    },
}

_instruction_type_ctx: ContextVar[Optional[str]] = ContextVar(
    "embedding_instruction_type", default=None
)


def _instructions_enabled() -> bool:
    config = get_embedding_config()
    mode = (config.embedding_instruction_mode or "off").strip().lower()
    return mode not in {"", "off", "false", "0", "disabled", "none"}


def normalize_instruction_type(instruction_type: Optional[str]) -> Optional[str]:
    if not instruction_type:
        return None
    lowered = instruction_type.strip().lower()
    if lowered in INSTRUCTION_CONFIG:
        return lowered
    return None


def push_instruction_type(instruction_type: Optional[str]) -> Optional[Token]:
    """Persist instruction type within the current async context."""
    normalized = normalize_instruction_type(instruction_type)
    if normalized is None:
        return None
    return _instruction_type_ctx.set(normalized)


def pop_instruction_type(token: Optional[Token]) -> None:
    """Reset the instruction type context token."""
    if token is not None:
        _instruction_type_ctx.reset(token)


@contextmanager
def instruction_scope(instruction_type: Optional[str]):
    """Context manager to temporarily override the instruction type."""
    token = push_instruction_type(instruction_type)
    try:
        yield
    finally:
        pop_instruction_type(token)


def get_active_instruction_type(explicit_type: Optional[str] = None) -> Optional[str]:
    """Resolve the active instruction profile."""
    normalized = normalize_instruction_type(explicit_type)
    if normalized:
        return normalized

    ctx_value = _instruction_type_ctx.get()
    if ctx_value:
        return ctx_value

    config = get_embedding_config()
    return normalize_instruction_type(config.embedding_instruction_default)


def _format_with_instruction(
    texts: Iterable[str], role: InstructionRole, instruction_type: Optional[str]
) -> List[str]:
    instruction = get_active_instruction_type(instruction_type)
    if not instruction:
        return [text for text in texts]

    template = INSTRUCTION_CONFIG.get(instruction)
    if not template:
        return [text for text in texts]

    prefix = template["query" if role == "query" else "passage"]
    return [f"{prefix}{text}" if text else prefix for text in texts]


def prepare_query_texts(
    texts: Iterable[str], instruction_type: Optional[str] = None
) -> List[str]:
    """Apply query instructions when enabled."""
    if not _instructions_enabled():
        return [text for text in texts]
    return _format_with_instruction(texts, "query", instruction_type)


def prepare_passage_texts(
    texts: Iterable[str], instruction_type: Optional[str] = None
) -> List[str]:
    """Apply passage instructions when enabled."""
    if not _instructions_enabled():
        return [text for text in texts]
    return _format_with_instruction(texts, "passage", instruction_type)


def list_instruction_types() -> List[str]:
    """Return supported instruction identifiers."""
    return sorted(INSTRUCTION_CONFIG.keys())
