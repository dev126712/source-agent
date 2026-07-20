"""Provider-agnostic LLM factory.

Returns a LangChain chat model based on the resolved provider. Keeping this
behind one function means every node/agent asks for a model the same way,
and switching providers is an env change, not a code change.
"""

from functools import lru_cache

from langchain_core.language_models.chat_models import BaseChatModel

from app.core.config import settings


@lru_cache
def get_llm(temperature: float = 0.0) -> BaseChatModel:
    provider = settings.resolved_llm_provider

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=settings.anthropic_model,
            api_key=settings.anthropic_api_key,
            temperature=temperature,
            max_tokens=2048,
        )

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=temperature,
        )

    if provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(
            model=settings.groq_model,
            api_key=settings.groq_api_key,
            temperature=temperature,
        )

    if provider == "ollama":
        from langchain_openai import ChatOpenAI

        # Ollama exposes an OpenAI-compatible endpoint.
        return ChatOpenAI(
            model=settings.ollama_model,
            base_url=f"{settings.ollama_base_url}/v1",
            api_key="ollama",
            temperature=temperature,
        )

    raise ValueError(f"Unknown LLM provider: {provider}")
