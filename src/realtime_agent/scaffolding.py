"""Agent scaffolding utilities.

This module centralises the logic for constructing agent-specific scaffolding
objects that provide template-driven prompts when a realtime session is
initialised.  The abstractions here are intentionally lightweight so that they
can be easily extended as new agent types are introduced.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from jinja2 import Template, TemplateError

from realtime_agent.questionnaire import (
    DEFAULT_QUESTIONNAIRE_PROMPT,
    Questionnaire,
)

__all__ = [
    "AgentScaffolding",
    "QuestionnaireAgentScaffolding",
    "create_scaffolding",
]


DEFAULT_QUESTIONNAIRE_TEMPLATE = (
    "Say 'Hello, this is {{ state.agent_name | default(\"Agent\") }} from "
    "{{ state.branch_name | default(\"our office\") }}, how can I help you today?'"
)

@runtime_checkable
class AgentScaffolding(Protocol):
    """Minimal interface describing the data required by a :class:`Session`."""

    def initial_message_template(self) -> str:
        """Return the template string for the initial message."""

    def render_questionnaire(self, state: Mapping[str, Any] | None = None) -> str | None:
        """Return the rendered questionnaire content for the initial exchange."""

    def tools(self) -> Sequence[Any] | None:
        """Return the tools that should be advertised for the session."""


@dataclass
class QuestionnaireAgentScaffolding:
    """Scaffolding for the ``questionnaire`` agent type."""

    template: str = DEFAULT_QUESTIONNAIRE_TEMPLATE
    questionnaire_template: str | None = None
    questionnaire_schema: Mapping[str, Any] | Sequence[Any] | None = None
    tools_config: Sequence[Any] | Mapping[str, Any] | None = None
    _built_questionnaire: str | None = field(init=False, default=None, repr=False)
    _built_state_snapshot: Mapping[str, Any] | None = field(init=False, default=None, repr=False)
    _tools_snapshot: tuple[Any, ...] | None = field(init=False, default=None, repr=False)

    def initial_message_template(self) -> str:
        return self.template

    def build_questionnaire(self, state: Mapping[str, Any] | None = None) -> str | None:
        """Eagerly build and cache the questionnaire payload for later rendering."""

        state_snapshot = self._snapshot_state(state)
        questionnaire = self._generate_questionnaire(state_snapshot)
        self._built_state_snapshot = state_snapshot
        self._built_questionnaire = questionnaire
        return questionnaire

    def render_questionnaire(self, state: Mapping[str, Any] | None = None) -> str | None:
        if state is None:
            if self._built_state_snapshot is not None:
                return self._built_questionnaire
            state_snapshot = self._snapshot_state(None)
            questionnaire = self._generate_questionnaire(state_snapshot)
            self._built_questionnaire = questionnaire
            self._built_state_snapshot = state_snapshot
            return questionnaire

        state_snapshot = self._snapshot_state(state)

        if self._built_state_snapshot is not None:
            built_state = dict(self._built_state_snapshot)
            if dict(state_snapshot) == built_state:
                return self._built_questionnaire

        questionnaire = self._generate_questionnaire(state_snapshot)
        self._built_questionnaire = questionnaire
        self._built_state_snapshot = state_snapshot
        return questionnaire

    def tools(self) -> Sequence[Any] | None:
        if self.tools_config is None:
            return ()

        if self._tools_snapshot is None:
            normalised: list[Any] = []
            source = self.tools_config
            if isinstance(source, Mapping):
                normalised.append(self._freeze_tool(source))
            else:
                for tool in source:
                    normalised.append(self._freeze_tool(tool))
            self._tools_snapshot = tuple(normalised)

        return tuple(self._clone_tool(tool) for tool in self._tools_snapshot)

    def _snapshot_state(self, state: Mapping[str, Any] | None) -> MappingProxyType:
        if state is None:
            return MappingProxyType({})
        if isinstance(state, MappingProxyType):
            return state
        return MappingProxyType(dict(state))

    def _generate_questionnaire(self, state_snapshot: Mapping[str, Any]) -> str | None:
        questionnaire = Questionnaire(
            template=self.questionnaire_template,
            schema=self.questionnaire_schema,
            fallback_prompt=DEFAULT_QUESTIONNAIRE_PROMPT,
        )
        return questionnaire.render(state_snapshot)

    @staticmethod
    def _freeze_tool(tool: Any) -> Any:
        if isinstance(tool, Mapping):
            return MappingProxyType(dict(tool))
        return tool

    @staticmethod
    def _clone_tool(tool: Any) -> Any:
        if isinstance(tool, MappingProxyType):
            return dict(tool)
        if isinstance(tool, Mapping):
            return dict(tool)
        return tool


def create_scaffolding(config: Mapping[str, Any] | None) -> AgentScaffolding | None:
    """Return an :class:`AgentScaffolding` instance for the provided config.

    Parameters
    ----------
    config:
        The ``config`` mapping provided when constructing a :class:`Session`.
    """

    if not config:
        return None

    agent_config = config.get("agent") if isinstance(config, Mapping) else None
    if not isinstance(agent_config, Mapping):
        return None

    agent_type = agent_config.get("type")
    template = agent_config.get("initial_message_template")
    questionnaire_template = agent_config.get("questionnaire_template")
    questionnaire_schema = agent_config.get("questionnaire")
    tools_config = agent_config.get("tools")

    if isinstance(questionnaire_template, str) and not questionnaire_template.strip():
        questionnaire_template = None

    if isinstance(questionnaire_schema, str) and not questionnaire_template:
        questionnaire_template = questionnaire_schema
        questionnaire_schema = None

    if isinstance(template, str) and not template.strip():
        template = None

    if agent_type == "questionnaire":
        if template is not None:
            return QuestionnaireAgentScaffolding(
                template=template,
                questionnaire_template=questionnaire_template,
                questionnaire_schema=questionnaire_schema,
                tools_config=_normalise_tools_config(tools_config),
            )
        return QuestionnaireAgentScaffolding(
            questionnaire_template=questionnaire_template,
            questionnaire_schema=questionnaire_schema,
            tools_config=_normalise_tools_config(tools_config),
        )

    if template is not None:
        return QuestionnaireAgentScaffolding(
            template=template,
            questionnaire_template=questionnaire_template,
            questionnaire_schema=questionnaire_schema,
            tools_config=_normalise_tools_config(tools_config),
        )

    return None


def _normalise_tools_config(tools: Any) -> Sequence[Any] | Mapping[str, Any] | None:
    if tools is None:
        return None
    if isinstance(tools, Mapping):
        return tools
    if isinstance(tools, Sequence) and not isinstance(tools, (str, bytes, bytearray)):
        return tuple(tools)
    return (tools,)


