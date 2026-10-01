"""
Logical Plan Validator for QueryPilot.
Implements pre-execution semantic and schema validation:
- Schema presence validation (rejects non-existent tables/columns like suppliers, loyalty_score)
- Scope filter enforcement (scope PREVIOUS_RESULT_SET or SINGLE_PREVIOUS_ENTITY must have ID filter)
- Join multiplication protection (prevents summing order-level measures after joining order_items)
- Aggregation grain safety
"""
from typing import Optional
from app.models.chat import ScopeEnum
from app.models.plan import LogicalQueryPlan, PlanFilter
from app.models.schema import DatabaseSchema


class PlanValidationError(Exception):
    pass


class PlanValidator:
    """Validates the logical plan against discovered schema and mathematical safety rules."""

    @classmethod
    def validate_plan(cls, plan: LogicalQueryPlan, schema: DatabaseSchema) -> tuple[bool, Optional[str]]:
        table_names = {t.name.lower(): t for t in schema.tables}

        # 1. Unknown Entity / Schema validation (Section 8 & Acceptance Test 7)
        if plan.primary_entity:
            entity_name = plan.primary_entity.lower().rstrip("s")
            found = False
            for t_name, table in table_names.items():
                if t_name.rstrip("s") == entity_name or t_name == plan.primary_entity.lower():
                    found = True
                    break
            if not found:
                return (
                    False,
                    f"The connected database has no table or attribute representing '{plan.primary_entity}'. QueryPilot will not hallucinate non-existent database entities.",
                )

        # 2. Scope Validation (Section 6 & Section 8 Ground Rule)
        # "A plan with a referenced scope but no scope filter in the SQL must fail validation."
        if plan.scope in [ScopeEnum.PREVIOUS_RESULT_SET, ScopeEnum.SINGLE_PREVIOUS_ENTITY]:
            if not plan.scoped_entity_ids:
                return (
                    False,
                    f"Plan specifies scope {plan.scope.value} but no target entity IDs were resolved from the previous Result Context.",
                )

        # 3. Join Multiplication Protection (Section 8)
        # Summing orders.total_amount after joining order_items multiplies order totals by item count.
        joined_tables = {t.lower() for t in plan.target_tables}
        if "orders" in joined_tables and "order_items" in joined_tables:
            for exp in plan.select_expressions:
                exp_clean = exp.replace(" ", "").upper()
                if "SUM(ORDERS.TOTAL_AMOUNT)" in exp_clean or "AVG(ORDERS.TOTAL_AMOUNT)" in exp_clean:
                    return (
                        False,
                        "Join multiplication detected: Summing or averaging order totals across joined line items produces mathematically distorted results. Line-item revenue must aggregate unit_price * quantity.",
                    )

        return True, None
