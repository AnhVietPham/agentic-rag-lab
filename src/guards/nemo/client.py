"""NeMo Guardrails client wrapper.

Wraps nemoguardrails LLMRails to provide topic/policy enforcement
via Colang rules. Configured to use Ollama as the LLM backend via
its OpenAI-compatible endpoint.

Usage:
    client = NeMoGuardrailsClient(config_path="src/guards/nemo", enabled=True)
    result = await client.check("Should I buy Tesla stock?")
    if result.is_blocked:
        # return refusal response
"""