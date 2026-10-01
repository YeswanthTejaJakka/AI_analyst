from abc import ABC, abstractmethod
from typing import Any, Optional
from app.models.chat import (
    ClarificationContext,
    ClarifyRequest,
    QueryClassificationEnum,
    QueryIntent,
    ResultContext,
)
from app.models.schema import DatabaseSchema, QueryResult


class LLMProvider(ABC):
    """Abstract interface for LLM providers (Gemini, OpenAI, Heuristic).

    Decouples complete NL database analyst pipeline into modular structured operations.
    """

    @abstractmethod
    async def generate_completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_schema: Optional[dict[str, Any]] = None,
        temperature: float = 0.1,
    ) -> str:
        """Generates a text or JSON completion from the LLM."""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Returns the name of the active provider."""
        pass

    @abstractmethod
    async def classify_query_relation(
        self,
        query: str,
        previous_intent: Optional[QueryIntent],
        previous_result_context: Optional[ResultContext],
        schema: DatabaseSchema,
        in_clarification: bool = False,
    ) -> QueryClassificationEnum:
        """Classify user query relative to conversation state BEFORE SQL generation."""
        pass

    @abstractmethod
    async def analyze_intent(
        self,
        query: str,
        schema: DatabaseSchema,
        classification: QueryClassificationEnum,
        previous_intent: Optional[QueryIntent] = None,
        previous_result_context: Optional[ResultContext] = None,
    ) -> QueryIntent:
        """Extract structured semantic intent (entity, operation, metrics, limit, filters, etc.)."""
        pass

    @abstractmethod
    async def detect_ambiguity(
        self,
        intent: QueryIntent,
        schema: DatabaseSchema,
        query: str,
        previous_result_context: Optional[ResultContext] = None,
    ) -> QueryIntent:
        """Detect metric, time, threshold, entity, or missing attribute ambiguities."""
        pass

    @abstractmethod
    async def resolve_clarification(
        self,
        user_response: str,
        clarification_context: ClarificationContext,
        schema: DatabaseSchema,
    ) -> tuple[bool, Optional[QueryIntent], Optional[str], Optional[dict[str, Any]]]:
        """Resolves clarification response (button click or free text). Returns (resolved, updated_intent, question_if_unresolved, options_if_unresolved)."""
        pass
