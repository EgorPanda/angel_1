from __future__ import annotations

from app.ai.agent import Agent
from app.ai.schemas import AgentOutcome, AgentRequest
from app.core.logging import get_logger

logger = get_logger("ai.runtime")


class AIRuntime:
    def __init__(self, core) -> None:
        self.core = core
        self.agent: Agent | None = None

    async def chat(self, text: str, user_id: str | None = None, correlation_id: str | None = None,
                   tool_names: list[str] | None = None, kind: str = "chat") -> AgentOutcome:
        self.ensure_agent()
        return await self.agent.run(
            AgentRequest(
                text=text,
                user_id=user_id,
                correlation_id=correlation_id,
                tool_names=tool_names,
                kind=kind,
            )
        )

    def ensure_agent(self) -> Agent:
        if self.agent is None:
            self.agent = Agent(self.core, self.core.llm)
        return self.agent

    def health_check(self) -> tuple[bool, str]:
        if self.core.llm is None:
            return False, "no LLM provider configured"
        return self.core.llm.health_check()