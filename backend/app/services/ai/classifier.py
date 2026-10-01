"""
Turn Classification module for QueryPilot.
Implements multi-class turn classification using structured LLM output or semantic state analysis.
Classes:
- NEW_QUERY
- FOLLOW_UP
- QUERY_REFINEMENT
- CORRECTION
- CLARIFICATION_RESPONSE
- RESULT_REFERENCE
- RESULT_EXPLANATION
- COMPARISON_WITH_PREVIOUS_RESULT
- CONTEXT_SWITCH
- UNRELATED_QUERY
"""
import json
import re
from typing import Any, Optional
from pydantic import BaseModel, Field

from app.models.chat import (
    ClarificationRequest,
    QueryClassificationEnum,
    QueryIntent,
    ResultContext,
)
from app.models.schema import DatabaseSchema
from app.services.ai.base import LLMProvider


class TurnClassificationResult(BaseModel):
    classification: QueryClassificationEnum
    confidence: float = 1.0
    relates_to_turn: Optional[int] = None
    rationale: str = ""


class TurnClassifier:
    """Classifies every user turn using conversation state, semantic intent, Result Context, and schema."""

    def __init__(self, llm_provider: Optional[LLMProvider] = None):
        self.llm_provider = llm_provider

    async def classify(
        self,
        query: str,
        previous_intent: Optional[QueryIntent],
        previous_result_context: Optional[ResultContext],
        pending_clarification: Optional[ClarificationRequest],
        schema: DatabaseSchema,
        turn_index: int = 1,
    ) -> TurnClassificationResult:
        # If an LLM provider (non-heuristic) is configured, use structured LLM classification
        if self.llm_provider and "Heuristic" not in self.llm_provider.get_provider_name():
            try:
                llm_result = await self._classify_with_llm(
                    query=query,
                    previous_intent=previous_intent,
                    previous_result_context=previous_result_context,
                    pending_clarification=pending_clarification,
                    schema=schema,
                    turn_index=turn_index,
                )
                if llm_result:
                    return llm_result
            except Exception:
                pass

        # Robust semantic classification
        return self._classify_semantic(
            query=query,
            previous_intent=previous_intent,
            previous_result_context=previous_result_context,
            pending_clarification=pending_clarification,
            schema=schema,
            turn_index=turn_index,
        )

    def _classify_semantic(
        self,
        query: str,
        previous_intent: Optional[QueryIntent],
        previous_result_context: Optional[ResultContext],
        pending_clarification: Optional[ClarificationRequest],
        schema: DatabaseSchema,
        turn_index: int,
    ) -> TurnClassificationResult:
        q_lower = query.lower().strip()

        # Rule 1: Pending clarification takes highest priority
        if pending_clarification:
            # Check if user explicitly aborts or context switches
            if any(term in q_lower for term in ["forget that", "cancel", "never mind", "start over", "ignore that", "reset"]):
                return TurnClassificationResult(
                    classification=QueryClassificationEnum.CONTEXT_SWITCH,
                    confidence=0.95,
                    relates_to_turn=turn_index - 1,
                    rationale="User explicitly cancelled pending clarification with context switch indicator",
                )
            # Otherwise, pending clarification takes precedence
            return TurnClassificationResult(
                classification=QueryClassificationEnum.CLARIFICATION_RESPONSE,
                confidence=0.98,
                relates_to_turn=turn_index - 1,
                rationale=f"User responded to pending clarification question regarding {pending_clarification.field_name}",
            )

        # Rule 2: Explicit Context Switch
        context_switch_patterns = [
            r"\bforget (that|about it)\b", r"\bnever mind\b", r"\bstart over\b",
            r"\blet'?s switch\b", r"\bswitch to\b", r"\bnow let'?s look at\b",
            r"\bignore previous\b", r"\bnew topic\b", r"\bclear context\b"
        ]
        for pattern in context_switch_patterns:
            if re.search(pattern, q_lower):
                return TurnClassificationResult(
                    classification=QueryClassificationEnum.CONTEXT_SWITCH,
                    confidence=0.95,
                    relates_to_turn=turn_index - 1 if previous_intent else None,
                    rationale="User explicitly instructed to switch context",
                )

        # Rule 3: Corrections
        correction_patterns = [
            r"\bi meant\b", r"\bi mean\b", r"\bi am asking\b", r"\bi'm asking\b",
            r"\bnot this\b", r"\bnot that\b", r"\binstead of\b", r"\bactually\b",
            r"\brather than\b", r"\bcorrection\b", r"\bmy bad\b"
        ]
        for pattern in correction_patterns:
            if re.search(pattern, q_lower):
                return TurnClassificationResult(
                    classification=QueryClassificationEnum.CORRECTION,
                    confidence=0.92,
                    relates_to_turn=turn_index - 1 if previous_intent else None,
                    rationale="User phrased input as a correction or explicit intent clarification",
                )

        # Rule 4: Query Refinement (modifying bounds, limits, filters, grains of current request)
        refinement_patterns = [
            r"\bmake that\b", r"\bchange that to\b", r"\bonly top\b", r"\bshow top\b",
            r"\bcategory wise\b", r"\bper category\b", r"\bi am asking total\b",
            r"\bgive me the total\b", r"\bjust the total\b", r"\bcombine them\b",
            r"\bonly completed\b", r"\bonly from\b", r"\bfilter by\b", r"\bby order count\b"
        ]
        for pattern in refinement_patterns:
            if re.search(pattern, q_lower):
                return TurnClassificationResult(
                    classification=QueryClassificationEnum.QUERY_REFINEMENT,
                    confidence=0.90,
                    relates_to_turn=turn_index - 1 if previous_intent else None,
                    rationale="User refined parameters or aggregation grain of the previous query",
                )

        # Rule 5: Pronoun and Demonstrative Result Reference
        reference_patterns = [
            r"\b(it|its|their|them|they|those|these|her|his|him)\b",
            r"\bthe (first|second|third|fourth|fifth|last) one\b",
            r"\b(2nd|3rd|4th|5th) one\b",
            r"\brunner up\b",
            r"\bthat (category|product|customer|order)\b",
            r"\bfrom them\b", r"\bby her\b", r"\bby him\b", r"\bby them\b",
            r"\bhow many are there\b", r"\bwhat category is it in\b"
        ]
        for pattern in reference_patterns:
            if re.search(pattern, q_lower):
                return TurnClassificationResult(
                    classification=QueryClassificationEnum.RESULT_REFERENCE,
                    confidence=0.95,
                    relates_to_turn=turn_index - 1 if previous_intent else None,
                    rationale="User message contains pronoun or demonstrative referencing previous result context",
                )

        # Rule 6: Result Explanation
        explanation_patterns = [
            r"\bwhy\b", r"\bhow come\b", r"\bexplain (this|the result|why)\b",
            r"\bbreakdown\b", r"\bhow was (this|that) calculated\b"
        ]
        for pattern in explanation_patterns:
            if re.search(pattern, q_lower):
                return TurnClassificationResult(
                    classification=QueryClassificationEnum.RESULT_EXPLANATION,
                    confidence=0.88,
                    relates_to_turn=turn_index - 1 if previous_intent else None,
                    rationale="User requested an explanation of previous results",
                )

        # Rule 7: Comparison with previous result
        comparison_patterns = [
            r"\bcompare (to|with|that)\b", r"\bhow does (that|this) compare\b",
            r"\bvs\b", r"\bversus\b", r"\bdifference between\b"
        ]
        for pattern in comparison_patterns:
            if re.search(pattern, q_lower):
                return TurnClassificationResult(
                    classification=QueryClassificationEnum.COMPARISON_WITH_PREVIOUS_RESULT,
                    confidence=0.85,
                    relates_to_turn=turn_index - 1 if previous_intent else None,
                    rationale="User asked for a comparative analysis with previous result",
                )

        # Rule 8: If previous intent exists and query is an elliptical follow-up ("what about India?", "and for 2025?")
        if previous_intent:
            if q_lower.startswith(("what about", "how about", "and for", "and in", "and with")):
                return TurnClassificationResult(
                    classification=QueryClassificationEnum.FOLLOW_UP,
                    confidence=0.90,
                    relates_to_turn=turn_index - 1,
                    rationale="Elliptical follow-up extending previous intent",
                )

        # Rule 9: Default to NEW_QUERY
        return TurnClassificationResult(
            classification=QueryClassificationEnum.NEW_QUERY,
            confidence=0.90,
            relates_to_turn=None,
            rationale="Query introduces a new independent semantic question",
        )

    async def _classify_with_llm(
        self,
        query: str,
        previous_intent: Optional[QueryIntent],
        previous_result_context: Optional[ResultContext],
        pending_clarification: Optional[ClarificationRequest],
        schema: DatabaseSchema,
        turn_index: int,
    ) -> Optional[TurnClassificationResult]:
        system_prompt = """You are QueryPilot's Turn Classifier.
Classify the user's message relative to the active conversation state.
Classes:
- NEW_QUERY: An independent query about a database entity or metric.
- FOLLOW_UP: A continuation or drill-down into the ongoing inquiry.
- QUERY_REFINEMENT: Altering the parameters, scope, or granularity of the immediate previous request.
- CORRECTION: Correcting a previous instruction ("I meant X, not Y").
- CLARIFICATION_RESPONSE: Answering a pending clarification question.
- RESULT_REFERENCE: Referencing entities from the previous result using pronouns or demonstratives (it, its, them, her, that category, the second one).
- RESULT_EXPLANATION: Asking why or how a result was derived.
- COMPARISON_WITH_PREVIOUS_RESULT: Comparing against a previous result set.
- CONTEXT_SWITCH: Explicitly abandoning the previous topic ("forget that", "now let's look at X").
- UNRELATED_QUERY: Chitchat or questions outside database analytics.

Return JSON:
{
  "classification": "<CLASS_NAME>",
  "confidence": 0.95,
  "relates_to_turn": 1,
  "rationale": "one-line reason"
}"""

        prompt = f"""Current user message: "{query}"
Pending clarification: {pending_clarification.model_dump_json() if pending_clarification else 'None'}
Previous intent: {previous_intent.model_dump_json() if previous_intent else 'None'}
Previous result context: {previous_result_context.model_dump_json() if previous_result_context else 'None'}
Tables in schema: {schema.get_table_names()}"""

        raw = await self.llm_provider.generate_completion(prompt=prompt, system_prompt=system_prompt)
        parsed = json.loads(raw)
        return TurnClassificationResult(
            classification=QueryClassificationEnum(parsed["classification"]),
            confidence=float(parsed.get("confidence", 0.9)),
            relates_to_turn=parsed.get("relates_to_turn"),
            rationale=parsed.get("rationale", ""),
        )
