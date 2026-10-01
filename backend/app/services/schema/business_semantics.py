from typing import Optional
from pydantic import BaseModel


class SemanticDefinition(BaseModel):
    term: str
    target_table: Optional[str] = None
    target_column: Optional[str] = None
    description: str
    filter_condition: Optional[str] = None
    calculation: Optional[str] = None


# Default business semantic definitions for common business & e-commerce metrics
DEFAULT_SEMANTICS: list[SemanticDefinition] = [
    SemanticDefinition(
        term="revenue",
        target_table="orders",
        target_column="total_amount",
        description="Total monetary value generated from fulfilled transactions. In business contexts, revenue usually only counts completed orders.",
        filter_condition="orders.status = 'completed'",
        calculation="SUM(orders.total_amount)",
    ),
    SemanticDefinition(
        term="sales",
        target_table="orders",
        target_column="total_amount",
        description="Gross sales value from completed orders.",
        filter_condition="orders.status = 'completed'",
        calculation="SUM(orders.total_amount)",
    ),
    SemanticDefinition(
        term="best customer",
        target_table="customers",
        description="Ambiguous term. Could mean highest total spending, most orders placed, or highest average order value.",
    ),
    SemanticDefinition(
        term="spending",
        target_table="orders",
        target_column="total_amount",
        description="Sum of order amounts paid by a customer.",
        calculation="SUM(orders.total_amount)",
    ),
    SemanticDefinition(
        term="average order value",
        target_table="orders",
        target_column="total_amount",
        description="Average total amount across completed orders.",
        filter_condition="orders.status = 'completed'",
        calculation="AVG(orders.total_amount)",
    ),
    SemanticDefinition(
        term="recent",
        description="Ambiguous time window. Typically implies the last 7 days, 30 days, or current quarter.",
    ),
    SemanticDefinition(
        term="active order",
        target_table="orders",
        target_column="status",
        description="Orders currently being processed or pending fulfillment.",
        filter_condition="orders.status = 'processing'",
    ),
    SemanticDefinition(
        term="completed order",
        target_table="orders",
        target_column="status",
        description="Orders successfully delivered and paid.",
        filter_condition="orders.status = 'completed'",
    ),
]


class BusinessSemanticLayer:
    """Manages semantic metadata and business metric definitions."""

    def __init__(self, custom_semantics: Optional[list[SemanticDefinition]] = None):
        self.definitions: list[SemanticDefinition] = list(DEFAULT_SEMANTICS)
        if custom_semantics:
            self.definitions.extend(custom_semantics)

    def find_relevant_semantics(self, query: str) -> list[SemanticDefinition]:
        query_lower = query.lower()
        matched = []
        for d in self.definitions:
            if d.term.lower() in query_lower:
                matched.append(d)
        return matched

    def to_prompt_text(self, query: str) -> str:
        matches = self.find_relevant_semantics(query)
        if not matches:
            return ""

        lines = ["Business Semantic Definitions:"]
        for m in matches:
            parts = [f"- '{m.term}': {m.description}"]
            if m.filter_condition:
                parts.append(f"Recommended filter: {m.filter_condition}")
            if m.calculation:
                parts.append(f"Standard formula: {m.calculation}")
            lines.append(" | ".join(parts))
        return "\n".join(lines)
