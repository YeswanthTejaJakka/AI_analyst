"""
QueryPilot Query Pipeline Orchestrator.
Implements the full NL → Intent → Schema → Ambiguity → SQL → Validate → Execute → Explain pipeline.
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.adapters.base import DatabaseAdapter
from app.core.config import settings
from app.models.chat import (
    ChatMessage,
    ClarificationContext,
    ClarificationRequest,
    ClarifyRequest,
    ConversationContext,
    ConversationStateEnum,
    QueryClassificationEnum,
    QueryIntent,
    ResultContext,
    StructuredConversationState,
)
from app.models.schema import DatabaseSchema, QueryResult
from app.services.ai.base import LLMProvider
from app.services.ai.factory import get_llm_provider
from app.services.schema.business_semantics import BusinessSemanticLayer
from app.services.sql.generator import SQLGenerator
from app.services.sql.validator import SQLValidator


class QueryPipeline:
    """Orchestrates the complete natural-language-to-result pipeline with explicit state machine management."""

    def __init__(self, llm_provider: Optional[LLMProvider] = None):
        self.llm_provider = llm_provider or get_llm_provider()
        self.sql_generator = SQLGenerator(llm_provider=self.llm_provider)
        self.semantic_layer = BusinessSemanticLayer()

    async def process_query(
        self,
        query: str,
        conversation: ConversationContext,
        schema: DatabaseSchema,
        adapter: DatabaseAdapter,
    ) -> ChatMessage:
        """Full pipeline: classification → intent → ambiguity check → SQL → execute → explain."""
        timestamp = datetime.now(timezone.utc).isoformat()
        message_id = uuid.uuid4().hex[:12]

        # 1. Classify query first to see if it's a NEW_QUERY, which would cancel clarification
        in_clarification = conversation.state == ConversationStateEnum.WAITING_FOR_CLARIFICATION or conversation.pending_clarification is not None
        
        classification = await self.llm_provider.classify_query_relation(
            query=query,
            previous_intent=conversation.last_intent,
            previous_result_context=conversation.last_result_context,
            schema=schema,
            in_clarification=in_clarification,
        )

        # 2. State Machine Check: If WAITING_FOR_CLARIFICATION and it's not a new query, process as clarification response!
        if in_clarification and conversation.pending_clarification and classification != QueryClassificationEnum.NEW_QUERY:
            conversation.state = ConversationStateEnum.RESOLVING_CLARIFICATION
            clarif_req = ClarifyRequest(
                field_name=conversation.pending_clarification.field_name,
                custom_input=query,
            )
            return await self.process_clarification(clarif_req, conversation, schema, adapter)

        # If it was a new query, cancel the clarification
        conversation.pending_clarification = None
        conversation.state = ConversationStateEnum.ANALYSING_QUERY

        # 3. Intent Extraction & Ambiguity Detection
        intent = await self.llm_provider.analyze_intent(
            query=query,
            schema=schema,
            classification=classification,
            previous_intent=conversation.last_intent,
            previous_result_context=conversation.last_result_context,
        )

        # Handle rejected (destructive) queries
        if intent.operation == "rejected":
            conversation.state = ConversationStateEnum.ERROR
            return ChatMessage(
                id=message_id,
                role="assistant",
                content=intent.unsupported_reason or "This operation is not permitted. QueryPilot only executes safe, read-only queries.",
                timestamp=timestamp,
                intent=intent,
                error="rejected",
                classification=classification,
            )

        # Handle unknown entities
        if intent.operation == "unknown_entity":
            conversation.state = ConversationStateEnum.ERROR
            return ChatMessage(
                id=message_id,
                role="assistant",
                content=intent.unsupported_reason or "I couldn't find the requested data in the database schema.",
                timestamp=timestamp,
                intent=intent,
                error="unknown_entity",
                classification=classification,
            )

        # Handle ambiguous queries → transition to WAITING_FOR_CLARIFICATION
        if intent.is_ambiguous and intent.clarification:
            conversation.state = ConversationStateEnum.WAITING_FOR_CLARIFICATION
            conversation.pending_clarification = intent.clarification
            conversation.last_intent = intent

            return ChatMessage(
                id=message_id,
                role="assistant",
                content=intent.clarification.question,
                timestamp=timestamp,
                intent=intent,
                clarification=intent.clarification,
                classification=classification,
                interpretation_text=self._build_interpretation_text(intent, classification),
            )

        # 4. Clear intent → generate, validate, execute SQL
        return await self._generate_and_execute(
            intent=intent,
            schema=schema,
            adapter=adapter,
            user_query=query,
            conversation=conversation,
            clarification_answer=None,
            message_id=message_id,
            timestamp=timestamp,
            classification=classification,
        )

    async def process_clarification(
        self,
        clarify_request: ClarifyRequest,
        conversation: ConversationContext,
        schema: DatabaseSchema,
        adapter: DatabaseAdapter,
    ) -> ChatMessage:
        """Process user's clarification answer (button click or free text)."""
        timestamp = datetime.now(timezone.utc).isoformat()
        message_id = uuid.uuid4().hex[:12]

        conversation.state = ConversationStateEnum.RESOLVING_CLARIFICATION

        user_answer = clarify_request.custom_input or clarify_request.selected_option or ""
        conversation.clarification_answers[clarify_request.field_name] = user_answer

        pending = conversation.pending_clarification
        intent = conversation.last_intent or QueryIntent()

        clarif_ctx = ClarificationContext(
            original_query=conversation.messages[-1].content if conversation.messages else "",
            current_intent=intent,
            missing_field=clarify_request.field_name,
            question=pending.question if pending else "",
            options=pending.options if pending else [],
        )

        resolved, updated_intent, follow_up_q, follow_up_opts = await self.llm_provider.resolve_clarification(
            user_response=user_answer,
            clarification_context=clarif_ctx,
            schema=schema,
        )

        if not resolved:
            # Clarification unresolved (e.g. user typed "highest" when threshold was asked - TEST 4 requirement)
            conversation.state = ConversationStateEnum.WAITING_FOR_CLARIFICATION
            new_clarification = ClarificationRequest(
                question=follow_up_q or "Could you please specify further?",
                options=follow_up_opts or [],
                field_name=clarify_request.field_name,
            )
            conversation.pending_clarification = new_clarification
            return ChatMessage(
                id=message_id,
                role="assistant",
                content=new_clarification.question,
                timestamp=timestamp,
                intent=intent,
                clarification=new_clarification,
                classification=QueryClassificationEnum.CLARIFICATION_RESPONSE,
            )

        final_intent = updated_intent or intent
        final_intent.is_ambiguous = False
        final_intent.clarification = None
        conversation.pending_clarification = None

        # Reconstruct user query from history
        user_query = ""
        for msg in reversed(conversation.messages):
            if msg.role == "user":
                user_query = msg.content
                break

        return await self._generate_and_execute(
            intent=final_intent,
            schema=schema,
            adapter=adapter,
            user_query=user_query,
            conversation=conversation,
            clarification_answer=user_answer,
            message_id=message_id,
            timestamp=timestamp,
            classification=QueryClassificationEnum.CLARIFICATION_RESPONSE,
        )

    async def _generate_and_execute(
        self,
        intent: QueryIntent,
        schema: DatabaseSchema,
        adapter: DatabaseAdapter,
        user_query: str,
        conversation: ConversationContext,
        clarification_answer: Optional[str],
        message_id: str,
        timestamp: str,
        classification: QueryClassificationEnum,
    ) -> ChatMessage:
        """Generate SQL, validate, execute, build result context, and explain."""
        try:
            conversation.state = ConversationStateEnum.GENERATING_SQL
            sql = await self.sql_generator.generate(
                intent=intent,
                schema=schema,
                user_query=user_query,
                clarification_answer=clarification_answer,
            )

            conversation.state = ConversationStateEnum.VALIDATING_SQL
            is_valid, validation_error = SQLValidator.validate_sql(sql, schema)
            if not is_valid:
                conversation.state = ConversationStateEnum.ERROR
                return ChatMessage(
                    id=message_id,
                    role="assistant",
                    content=f"I couldn't generate a valid query for this request. {validation_error}",
                    timestamp=timestamp,
                    intent=intent,
                    sql=sql,
                    error=validation_error,
                    classification=classification,
                )

            safe_sql = SQLValidator.enforce_row_limit(sql)

            conversation.state = ConversationStateEnum.EXECUTING_SQL
            result = adapter.execute_query(safe_sql)

            if result.error:
                conversation.state = ConversationStateEnum.ERROR
                return ChatMessage(
                    id=message_id,
                    role="assistant",
                    content=f"The query encountered an execution error: {result.error}",
                    timestamp=timestamp,
                    intent=intent,
                    sql=safe_sql,
                    query_result=result,
                    error=result.error,
                    execution_time_ms=result.execution_time_ms,
                    classification=classification,
                )

            conversation.state = ConversationStateEnum.SHOWING_RESULT

            # Build Result Context for follow-up reference resolution ("their", "them")
            returned_ids = []
            returned_names = []
            if result.rows and len(result.columns) > 0:
                for row in result.rows:
                    if len(row) > 0:
                        returned_ids.append(row[0])
                    if len(row) > 1 and isinstance(row[1], str):
                        returned_names.append(row[1])

            res_context = ResultContext(
                columns=result.columns,
                entity=intent.entity,
                row_count=result.row_count,
                returned_ids=returned_ids,
                returned_names=returned_names,
                query_intent=intent,
                sql=safe_sql,
            )

            explanation = await self._explain_result(
                intent=intent,
                sql=safe_sql,
                result=result,
                user_query=user_query,
                clarification_answer=clarification_answer,
                schema=schema,
            )

            # Update conversation context & state machine
            conversation.last_intent = intent
            conversation.last_sql = safe_sql
            conversation.last_result = result
            conversation.last_result_context = res_context
            conversation.state = ConversationStateEnum.IDLE

            return ChatMessage(
                id=message_id,
                role="assistant",
                content=explanation,
                timestamp=timestamp,
                intent=intent,
                sql=safe_sql,
                query_result=result,
                execution_time_ms=result.execution_time_ms,
                classification=classification,
                interpretation_text=self._build_interpretation_text(intent, classification),
            )

        except Exception as e:
            conversation.state = ConversationStateEnum.ERROR
            return ChatMessage(
                id=message_id,
                role="assistant",
                content=f"An unexpected error occurred while processing your query: {str(e)}",
                timestamp=timestamp,
                intent=intent,
                error=str(e),
                classification=classification,
            )

    @staticmethod
    def _build_interpretation_text(intent: QueryIntent, classification: QueryClassificationEnum) -> str:
        parts = []
        if intent.entity:
            parts.append(intent.entity.capitalize())
        if intent.operation:
            parts.append(intent.operation)
        if intent.primary_metric:
            parts.append(intent.primary_metric.replace("_", " "))
        if intent.sort_direction:
            parts.append(intent.sort_direction)
        if intent.limit:
            parts.append(f"limit {intent.limit}")
        return " → ".join(parts) if parts else classification.value

    async def _explain_result(
        self,
        intent: QueryIntent,
        sql: str,
        result: QueryResult,
        user_query: str,
        clarification_answer: Optional[str],
        schema: DatabaseSchema,
    ) -> str:
        if self.llm_provider and "Heuristic" not in self.llm_provider.get_provider_name():
            try:
                return await self._explain_with_llm(intent, sql, result, user_query, clarification_answer)
            except Exception:
                pass
        return self._explain_deterministic(intent, sql, result, user_query, clarification_answer)

    async def _explain_with_llm(
        self,
        intent: QueryIntent,
        sql: str,
        result: QueryResult,
        user_query: str,
        clarification_answer: Optional[str],
    ) -> str:
        preview_rows = result.rows[:10]
        result_preview = json.dumps(
            {"columns": result.columns, "rows": preview_rows, "total_rows": result.row_count},
            default=str,
        )

        system_prompt = """You are QueryPilot's result explainer.
Given a user's question, the SQL executed, and the query results, provide a clear, concise natural-language summary.
Rules:
1. Do NOT invent facts not present in the results.
2. Be specific with numbers and names from the results.
3. Keep the response brief (2-4 sentences).
4. If results are empty, say so clearly.
5. Use a professional, friendly tone."""

        prompt = f"""User asked: "{user_query}"
{f'Clarification: "{clarification_answer}"' if clarification_answer else ''}

SQL executed:
{sql}

Results ({result.row_count} rows, {result.execution_time_ms:.0f}ms):
{result_preview}

Provide a natural-language summary:"""

        return await self.llm_provider.generate_completion(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.2,
        )

    @staticmethod
    def _explain_deterministic(
        intent: QueryIntent,
        sql: str,
        result: QueryResult,
        user_query: str,
        clarification_answer: Optional[str],
    ) -> str:
        if result.row_count == 0:
            return "The query executed successfully, but no matching records were found."

        cols = result.columns
        rows = result.rows

        if intent.operation == "count" and result.row_count == 1 and len(cols) == 1:
            count_val = rows[0][0]
            entity = intent.entity or "records"
            return f"There are **{count_val:,}** {entity}s matching your request."

        if intent.operation == "ranking" and rows:
            entity = intent.entity or "record"
            name_col_idx = None
            value_col_idx = None
            for i, c in enumerate(cols):
                if c.lower() in ["name", "category_name", "product_name"]:
                    name_col_idx = i
                if c.lower() in ["price", "total_spending", "total_orders", "total_revenue", "total_units_sold", "average_order_value", "average_price"]:
                    value_col_idx = i

            if name_col_idx is not None and value_col_idx is not None:
                metric_name = cols[value_col_idx].replace("_", " ").title()
                if len(rows) == 1:
                    name = rows[0][name_col_idx]
                    val = rows[0][value_col_idx]
                    val_str = f"{val:,.2f}" if isinstance(val, (int, float)) else str(val)
                    return f"The top {entity} by {metric_name.lower()} is **{name}** with a {metric_name.lower()} of **{val_str}**."
                else:
                    lines = [f"Here are the top {len(rows)} {entity}s by {metric_name.lower()}:\n"]
                    for i, row in enumerate(rows[:10], 1):
                        name = row[name_col_idx]
                        val = row[value_col_idx]
                        val_str = f"{val:,.2f}" if isinstance(val, (int, float)) else str(val)
                        lines.append(f"{i}. **{name}** — {val_str}")
                    if result.row_count > 10:
                        lines.append(f"\n... and {result.row_count - 10} more.")
                    return "\n".join(lines)

        if result.row_count == 1:
            parts = []
            for i, c in enumerate(cols):
                val = rows[0][i]
                val_str = f"{val:,.2f}" if isinstance(val, (int, float)) else str(val)
                parts.append(f"**{c.replace('_', ' ').title()}**: {val_str}")
            return "Result: " + " | ".join(parts)

        summary = f"Query returned **{result.row_count}** rows"
        if result.truncated:
            summary += f" (limited to {settings.MAX_RETURNED_ROWS} rows)"
        summary += f" in {result.execution_time_ms:.0f}ms."
        return summary
