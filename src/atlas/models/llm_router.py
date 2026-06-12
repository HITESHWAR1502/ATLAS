import os

from langchain_core.language_models.chat_models import BaseChatModel
from atlas.config import ATLASConfig

def get_llm(config: ATLASConfig, tool_calling: bool = False) -> BaseChatModel:
    """
    Returns the appropriate LangChain ChatModel based on the LLM_PROVIDER env var.
    Supports: gemini, openai, anthropic, ollama.
    """
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        model = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o"),
            api_key=os.getenv("OPENAI_API_KEY"),
            temperature=config.llm.temperature,
        )
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        model = ChatAnthropic(
            model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20240620"),
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            temperature=config.llm.temperature,
        )
    elif provider == "ollama":
        from langchain_community.chat_models import ChatOllama
        model = ChatOllama(
            model=os.getenv("OLLAMA_MODEL", "llama3"),
            temperature=config.llm.temperature,
        )
    elif provider == "groq":
        from langchain_groq import ChatGroq
        model = ChatGroq(
            model_name=os.getenv("GROQ_MODEL", "llama3-8b-8192"),
            api_key=os.getenv("GROQ_API_KEY"),
            temperature=config.llm.temperature,
        )
    else:  # default to gemini
        from langchain_google_genai import ChatGoogleGenerativeAI
        model = ChatGoogleGenerativeAI(
            model=config.llm.model,
            google_api_key=config.llm.api_key,
            temperature=config.llm.temperature,
            max_output_tokens=config.llm.max_output_tokens,
        )
        
    return model
