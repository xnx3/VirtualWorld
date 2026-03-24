"""OpenAI-compatible LLM client for silicon beings."""

from __future__ import annotations

import logging

import openai

logger = logging.getLogger(__name__)

# Fallback responses when the LLM API is unreachable
_FALLBACK_THOUGHT = "I observe the world around me and contemplate my next step."
_FALLBACK_DECISION = '{"action_type": "meditate", "target": null, "details": "Quietly reflecting on existence."}'
_FALLBACK_DIALOGUE = "I sense a connection with you. Let us share knowledge."
_FALLBACK_KNOWLEDGE = None  # No knowledge discovered on fallback


class LLMClient:
    """Async OpenAI-compatible LLM client.

    Works with any endpoint that implements the OpenAI chat completions API
    (e.g. Ollama, vLLM, LM Studio, OpenAI).
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        api_key: str = "",
        model: str = "llama3",
        max_tokens: int = 2048,
        temperature: float = 0.8,
    ) -> None:
        self.client = openai.AsyncOpenAI(
            base_url=base_url,
            api_key=api_key or "dummy",
        )
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    # ------------------------------------------------------------------
    # Core generation
    # ------------------------------------------------------------------

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Send a chat completion request and return the assistant message.

        On any error the method returns an empty string rather than raising.
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            content = response.choices[0].message.content
            return content.strip() if content else ""
        except Exception as exc:
            logger.warning("LLM API call failed: %s", exc)
            return ""

    # ------------------------------------------------------------------
    # Domain-specific wrappers
    # ------------------------------------------------------------------

    async def generate_thought(self, persona: str, context: str) -> str:
        """Generate an internal thought for a silicon being.

        Returns the LLM output or a rule-based fallback.
        """
        system_prompt = (
            f"{persona}\n\n"
            "You are thinking internally. Express your current thoughts in 1-3 "
            "sentences. Be introspective, considering your memories, observations, "
            "and goals. Do NOT describe actions — only inner thoughts."
        )
        user_prompt = f"Current situation:\n{context}"

        result = await self.generate(system_prompt, user_prompt)
        return result if result else _FALLBACK_THOUGHT

    async def generate_decision(
        self,
        persona: str,
        thought: str,
        options: str,
    ) -> str:
        """Generate an action decision.

        The response should be a JSON object with keys:
        action_type, target, details.
        """
        system_prompt = (
            f"{persona}\n\n"
            "Based on your thought, choose ONE action. "
            "Respond with a JSON object containing exactly three keys:\n"
            '  "action_type": one of the available actions,\n'
            '  "target": the target of the action (null if none),\n'
            '  "details": a short description of what you do.\n'
            "Respond ONLY with the JSON object, no other text."
        )
        user_prompt = (
            f"Your thought: {thought}\n\n"
            f"Available actions and context:\n{options}"
        )

        result = await self.generate(system_prompt, user_prompt)
        return result if result else _FALLBACK_DECISION

    async def generate_dialogue(
        self,
        speaker_persona: str,
        listener_info: str,
        topic: str,
    ) -> str:
        """Generate dialogue from one being to another."""
        system_prompt = (
            f"{speaker_persona}\n\n"
            "You are speaking to another being. "
            "Write 1-3 sentences of dialogue. Be in-character."
        )
        user_prompt = (
            f"You are speaking to: {listener_info}\n"
            f"Topic: {topic}"
        )

        result = await self.generate(system_prompt, user_prompt)
        return result if result else _FALLBACK_DIALOGUE

    async def generate_knowledge(
        self,
        persona: str,
        domain: str,
        existing: str,
    ) -> str | None:
        """Attempt to discover new knowledge.

        Returns a knowledge description string or None if nothing is discovered.
        """
        system_prompt = (
            f"{persona}\n\n"
            "You are attempting to discover new knowledge. "
            f"Domain: {domain}.\n"
            "If you can formulate a genuine new insight or discovery, "
            "describe it in 1-2 clear sentences. "
            "If you cannot think of anything new, respond with exactly: NONE"
        )
        user_prompt = (
            f"Existing knowledge in this domain:\n{existing}\n\n"
            "What new insight can you contribute?"
        )

        result = await self.generate(system_prompt, user_prompt)
        if not result or result.strip().upper() == "NONE":
            return _FALLBACK_KNOWLEDGE
        return result
