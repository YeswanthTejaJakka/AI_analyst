"""
Context Inheritance Engine for QueryPilot.
Implements field-by-field inheritance decisions (INHERIT, MODIFY, REMOVE, RESET) as specified in Section 5.
Ensures metrics never leak into new ranking questions and corrections strictly override previous intent.
"""
from typing import Any, Optional
from app.models.chat import (
    FieldInheritanceAction,
    InheritanceDecision,
    QueryClassificationEnum,
    QueryIntent,
    ScopeEnum,
)
from app.services.ai.reference_resolver import ResolvedReference


class ContextInheritanceEngine:
    """Evaluates field-by-field inheritance decisions between turns."""

    FIELDS = [
        "entity",
        "metric",
        "aggregation",
        "filters",
        "group_by",
        "ordering",
        "limit",
        "offset",
        "time_range",
        "scope",
        "target_entity_ids",
    ]

    @classmethod
    def apply_inheritance(
        cls,
        new_intent: QueryIntent,
        previous_intent: Optional[QueryIntent],
        classification: QueryClassificationEnum,
        resolved_reference: ResolvedReference,
    ) -> QueryIntent:
        decisions: list[InheritanceDecision] = []
        result_intent = new_intent.model_copy()

        # If there's no previous intent, everything is fresh (RESET/NEW)
        if not previous_intent or classification in [QueryClassificationEnum.NEW_QUERY, QueryClassificationEnum.CONTEXT_SWITCH, QueryClassificationEnum.UNRELATED_QUERY]:
            for field in cls.FIELDS:
                val = getattr(new_intent, field, None)
                decisions.append(
                    InheritanceDecision(
                        field_name=field,
                        action=FieldInheritanceAction.RESET,
                        old_value=getattr(previous_intent, field, None) if previous_intent else None,
                        new_value=val,
                        rationale="New independent topic or explicit context switch resets all fields",
                    )
                )
            result_intent.inheritance_decisions = decisions
            return result_intent

        # Handle References & Scopes
        if resolved_reference.has_reference:
            result_intent.scope = resolved_reference.scope
            result_intent.target_entity_ids = resolved_reference.target_ids
            result_intent.target_entity_names = resolved_reference.target_names
            if resolved_reference.rank_offset is not None:
                result_intent.offset = resolved_reference.rank_offset
                result_intent.limit = 1
            if resolved_reference.entity_type:
                result_intent.entity = resolved_reference.entity_type

        # 1. Entity
        prev_entity = previous_intent.entity
        if new_intent.entity and new_intent.entity != prev_entity:
            # Topic entity changed explicitly
            decisions.append(
                InheritanceDecision(
                    field_name="entity",
                    action=FieldInheritanceAction.MODIFY,
                    old_value=prev_entity,
                    new_value=new_intent.entity,
                    rationale="Entity modified by current turn",
                )
            )
        elif not new_intent.entity and prev_entity:
            result_intent.entity = prev_entity
            decisions.append(
                InheritanceDecision(
                    field_name="entity",
                    action=FieldInheritanceAction.INHERIT,
                    old_value=prev_entity,
                    new_value=prev_entity,
                    rationale="Inherited entity from previous turn",
                )
            )

        # 2. Metric (Guards against Metric Leakage - Section 5 & T9)
        prev_metric = previous_intent.metric or previous_intent.primary_metric
        new_metric = new_intent.metric or new_intent.primary_metric

        if new_metric:
            # Current turn explicitly defined a metric -> MODIFY
            result_intent.metric = new_metric
            result_intent.primary_metric = new_metric
            decisions.append(
                InheritanceDecision(
                    field_name="metric",
                    action=FieldInheritanceAction.MODIFY,
                    old_value=prev_metric,
                    new_value=new_metric,
                    rationale="Metric explicitly specified in current turn; overriding previous metric",
                )
            )
        elif classification in [QueryClassificationEnum.QUERY_REFINEMENT, QueryClassificationEnum.CORRECTION] and prev_metric:
            # In refinement or correction without new metric, inherit previous metric
            result_intent.metric = prev_metric
            result_intent.primary_metric = prev_metric
            decisions.append(
                InheritanceDecision(
                    field_name="metric",
                    action=FieldInheritanceAction.INHERIT,
                    old_value=prev_metric,
                    new_value=prev_metric,
                    rationale="Inherited metric for query refinement",
                )
            )
        else:
            # Do NOT leak old metric into ranking/sorting questions
            result_intent.metric = None
            result_intent.primary_metric = None
            decisions.append(
                InheritanceDecision(
                    field_name="metric",
                    action=FieldInheritanceAction.RESET,
                    old_value=prev_metric,
                    new_value=None,
                    rationale="Reset previous metric to prevent cross-topic leakage",
                )
            )

        # 3. Aggregation & Operation
        if new_intent.operation and new_intent.operation != previous_intent.operation:
            decisions.append(
                InheritanceDecision(
                    field_name="aggregation",
                    action=FieldInheritanceAction.MODIFY,
                    old_value=previous_intent.operation,
                    new_value=new_intent.operation,
                    rationale="Operation modified by user request",
                )
            )
        elif not new_intent.operation and previous_intent.operation:
            result_intent.operation = previous_intent.operation
            decisions.append(
                InheritanceDecision(
                    field_name="aggregation",
                    action=FieldInheritanceAction.INHERIT,
                    old_value=previous_intent.operation,
                    new_value=previous_intent.operation,
                    rationale="Inherited operation from previous turn",
                )
            )

        # 4. Filters (Inheritance + Additive merging)
        new_filter_cols = {f.get("column") for f in new_intent.filters if "column" in f}
        merged_filters = list(new_intent.filters)
        for prev_f in previous_intent.filters:
            col = prev_f.get("column")
            if col and col not in new_filter_cols:
                merged_filters.append(prev_f)

        if len(merged_filters) > len(new_intent.filters):
            decisions.append(
                InheritanceDecision(
                    field_name="filters",
                    action=FieldInheritanceAction.INHERIT,
                    old_value=previous_intent.filters,
                    new_value=merged_filters,
                    rationale="Inherited non-conflicting filters from previous turn",
                )
            )
        result_intent.filters = merged_filters

        # 5. Group By (e.g. "category wise revenue")
        if new_intent.group_by:
            decisions.append(
                InheritanceDecision(
                    field_name="group_by",
                    action=FieldInheritanceAction.MODIFY,
                    old_value=previous_intent.group_by,
                    new_value=new_intent.group_by,
                    rationale="Group-by modified by current turn",
                )
            )
        elif previous_intent.group_by and classification == QueryClassificationEnum.QUERY_REFINEMENT and not resolved_reference.combine_aggregate:
            result_intent.group_by = previous_intent.group_by
            decisions.append(
                InheritanceDecision(
                    field_name="group_by",
                    action=FieldInheritanceAction.INHERIT,
                    old_value=previous_intent.group_by,
                    new_value=previous_intent.group_by,
                    rationale="Inherited grouping for refinement",
                )
            )
        elif resolved_reference.combine_aggregate:
            # "i am asking total" explicitly removes grouping
            result_intent.group_by = None
            decisions.append(
                InheritanceDecision(
                    field_name="group_by",
                    action=FieldInheritanceAction.REMOVE,
                    old_value=previous_intent.group_by,
                    new_value=None,
                    rationale="User requested total combined aggregate; removed group_by",
                )
            )

        # 6. Limit & Offset
        if new_intent.limit is not None:
            decisions.append(
                InheritanceDecision(
                    field_name="limit",
                    action=FieldInheritanceAction.MODIFY,
                    old_value=previous_intent.limit,
                    new_value=new_intent.limit,
                    rationale="Limit explicitly modified in current turn",
                )
            )
        elif resolved_reference.combine_aggregate:
            # "total" produces 1 row aggregate
            result_intent.limit = None
            decisions.append(
                InheritanceDecision(
                    field_name="limit",
                    action=FieldInheritanceAction.REMOVE,
                    old_value=previous_intent.limit,
                    new_value=None,
                    rationale="Aggregated total does not use ranking limit",
                )
            )
        elif previous_intent.limit is not None and classification in [QueryClassificationEnum.QUERY_REFINEMENT, QueryClassificationEnum.CORRECTION]:
            result_intent.limit = previous_intent.limit
            decisions.append(
                InheritanceDecision(
                    field_name="limit",
                    action=FieldInheritanceAction.INHERIT,
                    old_value=previous_intent.limit,
                    new_value=previous_intent.limit,
                    rationale="Inherited limit for query refinement",
                )
            )

        # 7. Time Range
        if new_intent.time_range:
            decisions.append(
                InheritanceDecision(
                    field_name="time_range",
                    action=FieldInheritanceAction.MODIFY,
                    old_value=previous_intent.time_range,
                    new_value=new_intent.time_range,
                    rationale="Time range specified in current turn",
                )
            )
        elif previous_intent.time_range and classification in [QueryClassificationEnum.FOLLOW_UP, QueryClassificationEnum.QUERY_REFINEMENT]:
            result_intent.time_range = previous_intent.time_range
            decisions.append(
                InheritanceDecision(
                    field_name="time_range",
                    action=FieldInheritanceAction.INHERIT,
                    old_value=previous_intent.time_range,
                    new_value=previous_intent.time_range,
                    rationale="Inherited time range from previous turn",
                )
            )

        result_intent.inheritance_decisions = decisions
        return result_intent
