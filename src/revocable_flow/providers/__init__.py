"""REST adapter registry. Importing it never reads credentials or calls a provider."""
from .anthropic_provider import AnthropicProvider
from .google_provider import GoogleProvider
from .openai_provider import OpenAIProvider
from .base import ModelProvider, ProviderError, ProviderResponse

PROVIDER_CLASSES = {"openai": OpenAIProvider, "anthropic": AnthropicProvider, "google": GoogleProvider}
