"""
Reference and Scope Resolution module for QueryPilot.
Implements pronoun, demonstrative, ordinal, multi-hop, and entity scope resolution against the Result Context stack.
"""
import re
from typing import Any, Optional
from pydantic import BaseModel, Field

from app.models.chat import ClarificationRequest, ResultContext, ScopeEnum
from app.models.schema import DatabaseSchema


class ResolvedReference(BaseModel):
    has_reference: bool = False
    scope: ScopeEnum = ScopeEnum.GLOBAL
    entity_type: Optional[str] = None
    target_ids: list[Any] = Field(default_factory=list)
    target_names: list[str] = Field(default_factory=list)
    rank_offset: Optional[int] = None
    traversed_path: list[str] = Field(default_factory=list)
    clarification_needed: Optional[ClarificationRequest] = None
    combine_aggregate: bool = False  # e.g., "total from them" -> combined sum


class ReferenceResolver:
    """Resolves references, pronouns, ordinals, and scopes against structured Result Context."""

    ORDINAL_MAP = {
        "first": 0, "1st": 0,
        "second": 1, "2nd": 1, "runner up": 1,
        "third": 2, "3rd": 2,
        "fourth": 3, "4th": 3,
        "fifth": 4, "5th": 4,
    }

    @classmethod
    def resolve(
        cls,
        query: str,
        result_context_stack: list[ResultContext],
        schema: DatabaseSchema,
    ) -> ResolvedReference:
        if not result_context_stack:
            return ResolvedReference(has_reference=False, scope=ScopeEnum.GLOBAL)

        latest_rc = result_context_stack[-1]
        q_lower = query.lower().strip()

        # 1. Ordinal References: "the second one", "2nd one", "runner up", "what about the second one"
        for word, idx in cls.ORDINAL_MAP.items():
            pattern = rf"\b(the\s+)?{word}(\s+one)?\b"
            if re.search(pattern, q_lower):
                # If the previous result has rows, bind to that row
                if latest_rc.result_rows and len(latest_rc.result_rows) > idx:
                    target_row = latest_rc.result_rows[idx]
                    target_id = target_row[0] if len(target_row) > 0 else None
                    target_name = target_row[1] if len(target_row) > 1 and isinstance(target_row[1], str) else None
                    return ResolvedReference(
                        has_reference=True,
                        scope=ScopeEnum.SINGLE_PREVIOUS_ENTITY,
                        entity_type=latest_rc.entity_type or latest_rc.entity,
                        target_ids=[target_id] if target_id is not None else [],
                        target_names=[target_name] if target_name is not None else [],
                        rank_offset=idx,
                    )
                # Or if asking to retrieve rank 2
                return ResolvedReference(
                    has_reference=True,
                    scope=ScopeEnum.SINGLE_PREVIOUS_ENTITY,
                    entity_type=latest_rc.entity_type or latest_rc.entity,
                    rank_offset=idx,
                )

        # 2. Singular Pronouns & References: "it", "its", "her", "his", "him", "by her", "by him"
        singular_pronouns = [r"\bits\b", r"\bher\b", r"\bhis\b", r"\bhim\b", r"\bby her\b", r"\bby him\b"]
        for p in singular_pronouns:
            if re.search(p, q_lower):
                # Look backwards in Result Context stack for a single entity or first row
                for rc in reversed(result_context_stack):
                    if rc.entity_ids:
                        target_id = rc.entity_ids[0]
                        target_name = rc.entity_names[0] if rc.entity_names else None
                        return ResolvedReference(
                            has_reference=True,
                            scope=ScopeEnum.SINGLE_PREVIOUS_ENTITY,
                            entity_type=rc.entity_type or rc.entity,
                            target_ids=[target_id],
                            target_names=[target_name] if target_name else [],
                        )

        # 3. Explicit demonstrative noun references: "that category", "that product", "that customer"
        for ent in ["category", "product", "customer", "order"]:
            if f"that {ent}" in q_lower or f"the {ent}" in q_lower:
                for rc in reversed(result_context_stack):
                    rc_entity = (rc.entity_type or rc.entity or "").lower().rstrip("s")
                    if rc_entity == ent and rc.entity_ids:
                        return ResolvedReference(
                            has_reference=True,
                            scope=ScopeEnum.SINGLE_PREVIOUS_ENTITY if len(rc.entity_ids) == 1 else ScopeEnum.PREVIOUS_RESULT_SET,
                            entity_type=ent,
                            target_ids=rc.entity_ids,
                            target_names=rc.entity_names,
                        )

        # 4. Multi-hop chains: "what category is it in?" -> product to category
        if "what category" in q_lower and ("it" in q_lower or "is it in" in q_lower):
            for rc in reversed(result_context_stack):
                rc_entity = (rc.entity_type or rc.entity or "").lower().rstrip("s")
                if rc_entity == "product" and rc.entity_ids:
                    return ResolvedReference(
                        has_reference=True,
                        scope=ScopeEnum.SINGLE_PREVIOUS_ENTITY,
                        entity_type="category",
                        target_ids=rc.entity_ids,
                        traversed_path=["product", "category"],
                    )

        # 5. Plural Pronouns & Result Set references: "they", "them", "their", "those", "these", "from them"
        plural_pronouns = [r"\bthem\b", r"\btheir\b", r"\bthey\b", r"\bthose\b", r"\bthese\b", r"\bfrom them\b", r"\bof them\b"]
        has_plural = any(re.search(p, q_lower) for p in plural_pronouns)

        # 6. Combined aggregate on previous result set: "give me the total", "i am asking total", "just the total"
        is_asking_total = bool(re.search(r"\b(i am asking total|give me the total|just the total|total revenue)\b", q_lower))

        if is_asking_total and latest_rc.entity_ids:
            return ResolvedReference(
                has_reference=True,
                scope=ScopeEnum.PREVIOUS_RESULT_SET,
                entity_type=latest_rc.entity_type or latest_rc.entity,
                target_ids=latest_rc.entity_ids,
                target_names=latest_rc.entity_names,
                combine_aggregate=True,
            )

        if has_plural:
            # Check attribute mismatch: e.g. previous result was "categories", query asks "their price"
            if (latest_rc.entity_type or latest_rc.entity) == "category" and "price" in q_lower:
                return ResolvedReference(
                    has_reference=True,
                    scope=ScopeEnum.PREVIOUS_RESULT_SET,
                    entity_type="product",
                    target_ids=latest_rc.entity_ids,
                    traversed_path=["category", "product"],
                    clarification_needed=ClarificationRequest(
                        field_name="category_price_definition",
                        question="Categories don't have a direct price, but products within them do. Would you like average product price or total product value?",
                        options=["Average product price per category", "Total product inventory value", "Top priced product in each category"],
                    ),
                )

            return ResolvedReference(
                has_reference=True,
                scope=ScopeEnum.PREVIOUS_RESULT_SET,
                entity_type=latest_rc.entity_type or latest_rc.entity,
                target_ids=latest_rc.entity_ids,
                target_names=latest_rc.entity_names,
            )

        return ResolvedReference(has_reference=False, scope=ScopeEnum.GLOBAL)
