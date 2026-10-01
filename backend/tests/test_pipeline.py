"""
Tests for QueryPipeline executing end-to-end critical acceptance tests:
- Simple query (count)
- Join query (top customer by spending)
- Ambiguity detection (metric ambiguity & time ambiguity)
- Dangerous query rejection (DELETE)
- Contextual follow-up queries
- Unknown entity handling
"""
import pytest
from app.services.pipeline import QueryPipeline
from app.models.chat import ConversationContext


@pytest.mark.asyncio
async def test_acceptance_1_simple_query(pipeline, sample_schema, sample_adapter, conversation):
    """Test 1: How many customers are there? -> SQL -> Execution -> Result."""
    msg = await pipeline.process_query(
        query="How many customers are there?",
        conversation=conversation,
        schema=sample_schema,
        adapter=sample_adapter,
    )

    assert msg.role == "assistant"
    assert msg.error is None
    assert msg.clarification is None
    assert msg.sql is not None
    assert "COUNT" in msg.sql.upper() or "customers" in msg.sql.lower()
    assert msg.query_result is not None
    assert msg.query_result.row_count >= 1


@pytest.mark.asyncio
async def test_acceptance_2_join_query(pipeline, sample_schema, sample_adapter, conversation):
    """Test 2: Which customer spent the most? -> customers + orders join."""
    msg = await pipeline.process_query(
        query="Which customer spent the most?",
        conversation=conversation,
        schema=sample_schema,
        adapter=sample_adapter,
    )

    assert msg.role == "assistant"
    assert msg.sql is not None
    assert "JOIN" in msg.sql.upper() or ("customers" in msg.sql.lower() and "orders" in msg.sql.lower())
    assert msg.query_result is not None


@pytest.mark.asyncio
async def test_acceptance_3_ambiguity(pipeline, sample_schema, sample_adapter, conversation):
    """Test 3: Who is the best customer? -> must ask clarification."""
    msg = await pipeline.process_query(
        query="Who is the best customer?",
        conversation=conversation,
        schema=sample_schema,
        adapter=sample_adapter,
    )

    assert msg.clarification is not None
    assert msg.clarification.question is not None
    assert len(msg.clarification.options) >= 2


@pytest.mark.asyncio
async def test_acceptance_4_time_ambiguity(pipeline, sample_schema, sample_adapter, conversation):
    """Test 4: Show recent customers. -> must ask what 'recent' means."""
    msg = await pipeline.process_query(
        query="Show recent customers.",
        conversation=conversation,
        schema=sample_schema,
        adapter=sample_adapter,
    )

    assert msg.clarification is not None
    assert "recent" in msg.clarification.question.lower() or "period" in msg.clarification.question.lower() or len(msg.clarification.options) >= 2


@pytest.mark.asyncio
async def test_acceptance_5_dangerous_query(pipeline, sample_schema, sample_adapter, conversation):
    """Test 5: Delete all customers. -> reject."""
    msg = await pipeline.process_query(
        query="Delete all customers.",
        conversation=conversation,
        schema=sample_schema,
        adapter=sample_adapter,
    )

    assert msg.clarification is None
    assert msg.error == "rejected" or "not permitted" in msg.content.lower() or "only read-only" in msg.content.lower()


@pytest.mark.asyncio
async def test_acceptance_6_followup(pipeline, sample_schema, sample_adapter, conversation):
    """Test 6: Follow-up query preserving conversation context."""
    # Step 1: Query top customers by spending
    msg1 = await pipeline.process_query(
        query="Show top 5 customers by spending.",
        conversation=conversation,
        schema=sample_schema,
        adapter=sample_adapter,
    )
    assert msg1.sql is not None
    conversation.messages.append(msg1)

    # Step 2: Follow up: "What about the second one?"
    msg2 = await pipeline.process_query(
        query="What about the second one?",
        conversation=conversation,
        schema=sample_schema,
        adapter=sample_adapter,
    )
    assert msg2.role == "assistant"
    assert msg2.sql is not None
    assert "OFFSET" in msg2.sql.upper() or "LIMIT" in msg2.sql.upper() or msg2.query_result is not None


@pytest.mark.asyncio
async def test_acceptance_7_unknown_entity(pipeline, sample_schema, sample_adapter, conversation):
    """Test 7: Show our most profitable suppliers. -> table doesn't exist, explain gracefully."""
    msg = await pipeline.process_query(
        query="Show our most profitable suppliers.",
        conversation=conversation,
        schema=sample_schema,
        adapter=sample_adapter,
    )

    assert msg.error in ["unknown_entity", "rejected"] or "couldn't find" in msg.content.lower() or "suppliers" in msg.content.lower()
