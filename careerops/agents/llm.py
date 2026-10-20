"""LLM providers used for structured extraction.

Deterministic policy stays authoritative everywhere: the model only proposes
structured facts (skills, years, sponsorship wording) that callers validate and
merge with rule-based results. When no provider is configured, ``get_llm()``
returns ``None`` and callers fall back to rules alone.

Settings are imported lazily so the extraction logic can be unit-tested
without the full application configuration.
"""
from __future__ import annotations

import json
import re


class LLMUnavailable(RuntimeError):
    """The configured provider could not produce a usable response."""


def parse_json_object(text: str) -> dict:
    """Parse the first JSON object in a model response."""
    match = re.search(r'\{.*\}', text or '', re.S)
    try:
        data = json.loads(match.group(0) if match else text)
    except (TypeError, ValueError) as exc:
        raise LLMUnavailable('model did not return valid JSON') from exc
    if not isinstance(data, dict):
        raise LLMUnavailable('model returned JSON that is not an object')
    return data


class LLMProvider:
    name = 'base'
    model = ''

    def complete_json(self, system: str, prompt: str) -> dict:
        raise NotImplementedError


class OpenAILLM(LLMProvider):
    """OpenAI Chat Completions in JSON mode (any OpenAI-compatible endpoint)."""
    name = 'openai'

    def __init__(self, api_key: str, model: str = 'gpt-4o-mini', base_url: str = 'https://api.openai.com/v1', timeout: float = 30.0):
        if not api_key:
            raise LLMUnavailable('OPENAI_API_KEY is not set')
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout

    def complete_json(self, system: str, prompt: str) -> dict:
        import httpx

        try:
            response = httpx.post(
                f'{self.base_url}/chat/completions',
                headers={'Authorization': f'Bearer {self.api_key}'},
                json={
                    'model': self.model,
                    'temperature': 0,
                    'response_format': {'type': 'json_object'},
                    'messages': [
                        {'role': 'system', 'content': system},
                        {'role': 'user', 'content': prompt},
                    ],
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            content = response.json()['choices'][0]['message']['content']
        except Exception as exc:
            raise LLMUnavailable(f'OpenAI request failed: {type(exc).__name__}') from exc
        return parse_json_object(content)


class BedrockLLM(LLMProvider):
    name = 'bedrock'

    def __init__(self, region: str, model_id: str):
        import boto3

        self.client = boto3.client('bedrock-runtime', region_name=region)
        self.model = model_id

    def complete_json(self, system: str, prompt: str) -> dict:
        try:
            response = self.client.converse(
                modelId=self.model,
                system=[{'text': system + '\nReturn only valid JSON.'}],
                messages=[{'role': 'user', 'content': [{'text': prompt}]}],
                inferenceConfig={'temperature': 0, 'maxTokens': 2000},
            )
            text = response['output']['message']['content'][0]['text']
        except Exception as exc:
            raise LLMUnavailable(f'Bedrock request failed: {type(exc).__name__}') from exc
        return parse_json_object(text)


def get_llm() -> LLMProvider | None:
    """Return the configured provider, or None when running rules-only.

    LLM_PROVIDER: ``openai`` | ``bedrock`` | ``local`` (default: rules only).
    """
    from careerops.core.config import settings

    provider = (settings.llm_provider or 'local').strip().lower()
    try:
        if provider == 'openai':
            return OpenAILLM(settings.openai_api_key or '', settings.openai_model, settings.openai_base_url)
        if provider == 'bedrock':
            return BedrockLLM(settings.aws_region, settings.bedrock_model_id)
    except LLMUnavailable:
        return None
    return None
