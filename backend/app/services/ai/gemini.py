"""
Google Gemini LLM Provider for QueryPilot.
Implements the complete LLMProvider interface using structured JSON prompts.
"""
import json
import re
from typing import Any, Optional
import httpx

from app.models.chat import (
    AmbiguityItem,
    ClarificationContext,
    ClarificationRequest,
    QueryClassificationEnum,
    QueryIntent,
    ResultContext,
    ScopeEnum,
)
from app.models.schema import DatabaseSchema
from app.services.ai.base import LLMProvider
from app.services.schema.retrieval import SchemaRetriever


class GeminiProvider(LLMProvider):
    """Google Gemini LLM Provider via standard REST API.

    Implements the full QueryPilot LLMProvider interface:
    - generate_completion (raw text/JSON)
    - classify_query_relation (turn classification)
    - analyze_intent (structured intent extraction)
    - detect_ambiguity
    - resolve_clarification
    """

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.model = model
        self.base_url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        )

    def get_provider_name(self) -> str:
        return f"Gemini ({self.model})"

    # ------------------------------------------------------------------
    # Core LLM completion
    # ------------------------------------------------------------------

    async def generate_completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_schema: Optional[dict[str, Any]] = None,
        temperature: float = 0.1,
    ) -> str:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not configured.")

        url = f"{self.base_url}?key={self.api_key}"

        contents = []
        if prompt:
            contents.append({"role": "user", "parts": [{"text": prompt}]})

        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
            },
        }

        if system_prompt:
            body["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        if json_schema:
            body["generationConfig"]["responseMimeType"] = "application/json"
            body["generationConfig"]["responseSchema"] = json_schema

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=body)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Gemini API returned error {resp.status_code}: {resp.text}"
                )

            data = resp.json()
            try:
                candidate = data["candidates"][0]
                text = candidate["content"]["parts"][0]["text"]
                return text
            except (KeyError, IndexError) as e:
                raise RuntimeError(f"Malformed Gemini response: {data}") from e

    # ------------------------------------------------------------------
    # Turn classification
    # ------------------------------------------------------------------

    async def classify_query_relation(
        self,
        query: str,
        previous_intent: Optional[QueryIntent],
        previous_result_context: Optional[ResultContext],
        schema: DatabaseSchema,
        in_clarification: bool = False,
    ) -> QueryClassificationEnum:
        # If user is mid-clarification and doesn't cancel, treat as CLARIFICATION_RESPONSE
        if in_clarification:
            cancel_terms = ["forget that", "never mind", "start over", "cancel", "new topic"]
            if not any(t in query.lower() for t in cancel_terms):
                return QueryClassificationEnum.CLARIFICATION_RESPONSE

        system_prompt = """You are QueryPilot's Turn Classifier.
Classify the user's message with one of these labels:
NEW_QUERY, FOLLOW_UP, QUERY_REFINEMENT, CORRECTION, CLARIFICATION_RESPONSE,
RESULT_REFERENCE, RESULT_EXPLANATION, COMPARISON_WITH_PREVIOUS_RESULT, CONTEXT_SWITCH, UNRELATED_QUERY.

Return JSON: {"classification": "LABEL", "confidence": 0.95}"""

        prev_intent_text = previous_intent.model_dump_json() if previous_intent else "None"
        prev_rc_text = (
            previous_result_context.model_dump_json() if previous_result_context else "None"
        )

        prompt = f"""User message: "{query}"
In clarification flow: {in_clarification}
Previous intent: {prev_intent_text}
Previous result context: {prev_rc_text}
Tables: {schema.get_table_names()}"""

        schema_def = {
            "type": "object",
            "properties": {
                "classification": {"type": "string"},
                "confidence": {"type": "number"},
            },
            "required": ["classification"],
        }
        raw = await self.generate_completion(
            prompt=prompt, system_prompt=system_prompt, json_schema=schema_def
        )
        parsed = json.loads(raw)
        try:
            return QueryClassificationEnum(parsed["classification"])
        except (ValueError, KeyError):
            return QueryClassificationEnum.NEW_QUERY

    # ------------------------------------------------------------------
    # Intent analysis
    # ------------------------------------------------------------------

    async def analyze_intent(
        self,
        query: str,
        schema: DatabaseSchema,
        classification: QueryClassificationEnum,
        previous_intent: Optional[QueryIntent] = None,
        previous_result_context: Optional[ResultContext] = None,
    ) -> QueryIntent:
        """Extract structured semantic intent using Gemini with JSON schema enforcement."""
        relevant_tables = SchemaRetriever.get_relevant_tables(schema, query)
        schema_text = schema.to_summary_text(relevant_tables)

        system_prompt = f"""You are QueryPilot's Intent Extractor.
Extract a precise structured intent from the user's natural-language query.

Turn classification: {classification.value}

Schema:
{schema_text}

Rules:
1. For FOLLOW_UP, QUERY_REFINEMENT, CORRECTION, RESULT_REFERENCE — start from previous_intent and modify fields.
2. For NEW_QUERY or CONTEXT_SWITCH — always start fresh.
3. Detect ambiguous queries: "best customer", "popular product", "recent orders", "expensive" without threshold.
4. For references to previous result (pronouns/demonstratives), resolve them via previous_result_context.
5. NEVER include "drop", "delete", "update", "insert", "alter" operations — return operation="rejected".
6. Return operation="unknown_entity" if the user references data not in the schema.

Available operations: ranking, aggregation, retrieval, count, filter, comparison, rejected, unknown_entity
Available aggregation_functions: SUM, COUNT, AVG, MIN, MAX

Return JSON with this structure:
{{
  "entity": "product|customer|category|order|null",
  "operation": "ranking|aggregation|retrieval|count|filter|comparison|rejected|unknown_entity",
  "primary_metric": "revenue|spending|price|order_count|units_sold|avg_price|null",
  "metrics": [],
  "aggregation": "SUM|COUNT|AVG|MIN|MAX|null",
  "filters": {{}},
  "group_by": null,
  "sort_column": null,
  "sort_direction": "descending",
  "limit": null,
  "offset": null,
  "time_range": null,
  "scope": "GLOBAL|PREVIOUS_RESULT_SET|SINGLE_PREVIOUS_ENTITY",
  "referenced_ids": [],
  "is_ambiguous": false,
  "ambiguities": [],
  "clarification": null,
  "unsupported_reason": null
}}"""

        prompt = f"""User query: "{query}"

Previous intent:
{previous_intent.model_dump_json() if previous_intent else 'null'}

Previous result context:
{previous_result_context.model_dump_json() if previous_result_context else 'null'}

Extract the intent:"""

        intent_schema = {
            "type": "object",
            "properties": {
                "entity": {"type": "string"},
                "operation": {"type": "string"},
                "primary_metric": {"type": "string"},
                "metrics": {"type": "array", "items": {"type": "string"}},
                "aggregation": {"type": "string"},
                "filters": {"type": "object"},
                "group_by": {"type": "string"},
                "sort_column": {"type": "string"},
                "sort_direction": {"type": "string"},
                "limit": {"type": "integer"},
                "offset": {"type": "integer"},
                "time_range": {"type": "string"},
                "scope": {"type": "string"},
                "referenced_ids": {"type": "array", "items": {}},
                "is_ambiguous": {"type": "boolean"},
                "unsupported_reason": {"type": "string"},
            },
        }

        raw = await self.generate_completion(
            prompt=prompt, system_prompt=system_prompt, json_schema=intent_schema, temperature=0.05
        )
        data = json.loads(raw)

        # Resolve referenced_ids from result context if scope indicates it
        ref_ids: list[Any] = data.get("referenced_ids") or []
        if not ref_ids and previous_result_context:
            scope_str = data.get("scope", "GLOBAL")
            if scope_str in ("PREVIOUS_RESULT_SET", "SINGLE_PREVIOUS_ENTITY"):
                ref_ids = previous_result_context.returned_ids or []

        # Build clarification if ambiguous
        clarification = None
        ambiguities = []
        if data.get("is_ambiguous"):
            # Build a generic clarification for each ambiguity dimension
            clarification = ClarificationRequest(
                field_name=data.get("primary_metric") or "metric",
                question=f"Your question about '{query}' has multiple interpretations. Could you clarify?",
                options=data.get("metrics") or [],
            )

        return QueryIntent(
            entity=data.get("entity"),
            operation=data.get("operation"),
            primary_metric=data.get("primary_metric"),
            metrics=data.get("metrics") or [],
            aggregation=data.get("aggregation"),
            filters=data.get("filters") or {},
            group_by=data.get("group_by"),
            sort_column=data.get("sort_column"),
            sort_direction=data.get("sort_direction") or "descending",
            limit=data.get("limit"),
            offset=data.get("offset"),
            time_range=data.get("time_range"),
            scope=ScopeEnum(data.get("scope") or "GLOBAL"),
            referenced_ids=ref_ids,
            is_ambiguous=bool(data.get("is_ambiguous", False)),
            ambiguities=ambiguities,
            clarification=clarification,
            unsupported_reason=data.get("unsupported_reason"),
        )

    # ------------------------------------------------------------------
    # Ambiguity detection
    # ------------------------------------------------------------------

    async def detect_ambiguity(
        self,
        intent: QueryIntent,
        schema: DatabaseSchema,
        query: str,
        previous_result_context: Optional[ResultContext] = None,
    ) -> QueryIntent:
        """Post-process intent for ambiguities not caught during initial extraction."""
        # Fast path: already detected as ambiguous or is rejected/unknown
        if intent.is_ambiguous or intent.operation in ("rejected", "unknown_entity"):
            return intent

        # Check for common ambiguous intents not yet resolved
        q_lower = query.lower()
        if "best customer" in q_lower or "top customer" in q_lower:
            if not intent.primary_metric:
                intent.is_ambiguous = True
                intent.clarification = ClarificationRequest(
                    field_name="metric",
                    question="What defines the 'best customer'?",
                    options=["Highest total spending", "Most orders placed", "Highest average order value"],
                )
        if "popular" in q_lower and not intent.primary_metric:
            intent.is_ambiguous = True
            intent.clarification = ClarificationRequest(
                field_name="metric",
                question="What defines a 'popular' product?",
                options=["Highest units sold", "Most orders placed", "Highest revenue"],
            )
        if re.search(r"\brecently?\b", q_lower) and not intent.time_range:
            intent.is_ambiguous = True
            intent.clarification = ClarificationRequest(
                field_name="time_range",
                question="How recent should 'recent' be?",
                options=["Last 7 days", "Last 30 days", "Last 90 days", "This year"],
            )

        return intent

    # ------------------------------------------------------------------
    # Clarification resolution
    # ------------------------------------------------------------------

    async def resolve_clarification(
        self,
        user_response: str,
        clarification_context: ClarificationContext,
        schema: DatabaseSchema,
    ) -> tuple[bool, Optional[QueryIntent], Optional[str], Optional[dict[str, Any]]]:
        """Resolve a clarification response using Gemini."""
        system_prompt = """You are QueryPilot's Clarification Resolver.
Given a user's clarification response, determine if it resolves the pending question.
If resolved, return the updated intent fields. If not resolved, provide a better follow-up question.

Return JSON:
{
  "resolved": true,
  "updated_fields": {"primary_metric": "spending", "operation": "ranking"},
  "follow_up_question": null,
  "follow_up_options": null
}"""

        intent = clarification_context.current_intent
        prompt = f"""Clarification question: "{clarification_context.question}"
Options presented: {clarification_context.options}
User responded: "{user_response}"
Missing field: "{clarification_context.missing_field}"
Current intent: {intent.model_dump_json()}"""

        resolve_schema = {
            "type": "object",
            "properties": {
                "resolved": {"type": "boolean"},
                "updated_fields": {"type": "object"},
                "follow_up_question": {"type": "string"},
                "follow_up_options": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["resolved"],
        }

        try:
            raw = await self.generate_completion(
                prompt=prompt, system_prompt=system_prompt, json_schema=resolve_schema
            )
            data = json.loads(raw)
        except Exception:
            # Fallback: assume resolved and pass through
            intent.is_ambiguous = False
            intent.clarification = None
            return True, intent, None, None

        if data.get("resolved", False):
            updated_fields = data.get("updated_fields") or {}
            updated_intent = intent.model_copy(deep=True)
            for field, value in updated_fields.items():
                if hasattr(updated_intent, field):
                    setattr(updated_intent, field, value)
            updated_intent.is_ambiguous = False
            updated_intent.clarification = None
            return True, updated_intent, None, None
        else:
            return (
                False,
                None,
                data.get("follow_up_question") or "Could you clarify further?",
                data.get("follow_up_options") or [],
            )
