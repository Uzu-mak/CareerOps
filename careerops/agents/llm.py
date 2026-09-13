from __future__ import annotations
import json
import re
import boto3
from careerops.core.config import settings


class LLMProvider:
    name = 'base'
    def complete_json(self, system: str, prompt: str) -> dict:
        raise NotImplementedError
    def complete_text(self, system: str, prompt: str) -> str:
        raise NotImplementedError


class BedrockLLM(LLMProvider):
    name = 'bedrock'
    def __init__(self):
        self.client = boto3.client('bedrock-runtime', region_name=settings.aws_region)

    def _converse(self, system: str, prompt: str) -> str:
        response = self.client.converse(
            modelId=settings.bedrock_model_id,
            system=[{'text': system}],
            messages=[{'role': 'user', 'content': [{'text': prompt}]}],
            inferenceConfig={'temperature': 0.2, 'maxTokens': 3000},
        )
        return response['output']['message']['content'][0]['text']

    def complete_text(self, system: str, prompt: str) -> str:
        return self._converse(system, prompt)

    def complete_json(self, system: str, prompt: str) -> dict:
        text = self._converse(system + '\nReturn only valid JSON.', prompt)
        match = re.search(r'\{.*\}', text, re.S)
        return json.loads(match.group(0) if match else text)


class LocalLLM(LLMProvider):
    """Deterministic local fallback so the product works without cloud credentials.

    It deliberately does not pretend to be a general LLM. Specialized agents provide
    structured heuristics/templates and use Bedrock when configured.
    """
    name = 'local'
    def complete_json(self, system: str, prompt: str) -> dict:
        return {'note': 'local-provider', 'prompt_excerpt': prompt[:300]}
    def complete_text(self, system: str, prompt: str) -> str:
        return prompt


def get_llm() -> LLMProvider:
    if settings.llm_provider.lower() == 'bedrock':
        return BedrockLLM()
    return LocalLLM()
