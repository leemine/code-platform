"""Native model-call capture for prompt suggestions."""
from typing import Any
from openjiuwen.core.single_agent.rail.base import AgentCallbackContext, AgentRail
from . import prompt_suggestion

class PromptSuggestionForkRail(AgentRail):
    """Keep each turn's latest main model call for the fork (src-raw ``saveCacheSafeParams``).

    A call is kept under the session it ran in. DeepAgent makes it on its inner ReActAgent, in a
    callback context of its own, and the conversation's agent runs in the conversation's session. A
    subagent sharing these rails (the general-purpose one) runs in a session of its own, which no turn
    of the person's waits on.
    """

    # Read the call after every rail that rewrites it.
    priority = -1_000_000
    # The agent's session-state reader; the conversation's DeepAgent keeps the session's plan mode there.
    _load_state: Any = None

    def init(self, agent: Any) -> None:
        self._load_state = getattr(agent, "load_state", None)

    async def after_model_call(self, ctx: AgentCallbackContext) -> None:
        # An error here would fail the answer the call just gave; a call without a session or
        # model client has nothing to fork.
        llm = getattr(ctx.agent, "_llm", None)
        if ctx.session is None or llm is None:
            return
        planning = self._load_state is not None and self._load_state(ctx.session).plan_mode.mode == "plan"
        prompt_suggestion.forks.saw_main_call(ctx.session.get_session_id(), prompt_suggestion._MainCall(
            llm=llm, model=ctx.agent.config.model_name, messages=tuple(ctx.inputs.messages),
            tools=ctx.inputs.tools, answer=ctx.inputs.response, max_iterations=ctx.agent.config.max_iterations,
            planning=planning,
        ))


