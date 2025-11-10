"""Questionnaire rendering utilities.

This module provides a light-weight representation of a questionnaire payload
that can be rendered against the current session state.  The abstraction keeps
the rendering rules colocated so that other parts of the system can focus on
coordination concerns (such as caching or transport) without duplicating the
templating logic.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from copy import deepcopy
from types import MappingProxyType
from typing import Any, Callable, Iterable

from jinja2 import Template, TemplateError

__all__ = [
    "DEFAULT_QUESTIONNAIRE_PROMPT",
    "Questionnaire",
    "QuestionnaireSection",
    "QuestionnaireQuestion",
]


DEFAULT_QUESTIONNAIRE_PROMPT = (
    "Please provide the requested information so we can personalise your experience."
)


def _snapshot_state(state: Mapping[str, Any] | None) -> MappingProxyType:
    if state is None:
        return MappingProxyType({})
    if isinstance(state, MappingProxyType):
        return state
    return MappingProxyType(dict(state))


@dataclass(slots=True)
class QuestionnaireQuestion:
    """Define a single question within a questionnaire section."""

    question_id: str
    question_text: str
    question_type: str = "text"
    question_options: Sequence[str] | None = field(default_factory=tuple)
    skippable: bool = True
    value: Any | None = None
    skipped: bool = False
    _option_lookup: dict[str, str] = field(init=False, default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        for field_name, value in (
            ("question_id", self.question_id),
            ("question_text", self.question_text),
            ("question_type", self.question_type),
        ):
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")
            if not value:
                raise ValueError(f"{field_name} must be a non-empty string")

        options = self.question_options
        if options is None:
            options_iterable: list[str] = []
        else:
            if isinstance(options, (str, bytes)):
                raise TypeError("question_options must be a sequence of strings")
            if not isinstance(options, Sequence):
                raise TypeError("question_options must be a sequence of strings")
            options_iterable = list(options)

        option_lookup: dict[str, str] = {}
        for option in options_iterable:
            if not isinstance(option, str):
                raise TypeError("question_options must only contain strings")
            if not option:
                raise ValueError("question_options must contain non-empty strings")
            lowered = option.casefold()
            if lowered in option_lookup:
                raise ValueError(
                    "question_options must not contain duplicate values ignoring case"
                )
            option_lookup[lowered] = option

        if not isinstance(self.skippable, bool):
            raise TypeError("skippable must be a boolean")
        if not isinstance(self.skipped, bool):
            raise TypeError("skipped must be a boolean")
        if self.skipped and not self.skippable:
            raise ValueError("Non-skippable questions cannot be initialised as skipped")

        object.__setattr__(self, "question_options", list(options_iterable))
        object.__setattr__(self, "_option_lookup", option_lookup)

    def set_value(self, value: Any) -> None:
        canonical_value = value
        if self.question_options:
            if isinstance(value, str):
                matched_option = self._option_lookup.get(value.casefold())
                if matched_option is not None:
                    canonical_value = matched_option
            if canonical_value not in self.question_options:
                raise ValueError(
                    f"Value for question '{self.question_id}' must be one of "
                    f"{', '.join(repr(option) for option in self.question_options)}"
                )
        object.__setattr__(self, "value", canonical_value)
        object.__setattr__(self, "skipped", False)

    def clear_value(self) -> None:
        object.__setattr__(self, "value", None)
        object.__setattr__(self, "skipped", False)

    def skip(self) -> None:
        if not self.skippable:
            raise ValueError("Cannot skip a non-skippable question")
        object.__setattr__(self, "value", None)
        object.__setattr__(self, "skipped", True)

    def unskip(self) -> None:
        object.__setattr__(self, "skipped", False)

    def to_mapping(self) -> Mapping[str, Any]:
        return {
            "question_id": self.question_id,
            "question_text": self.question_text,
            "question_type": self.question_type,
            "question_options": list(self.question_options),
            "skippable": self.skippable,
            "value": self.value,
            "skipped": self.skipped,
        }


@dataclass(slots=True)
class QuestionnaireSection:
    """Represent a logical grouping of questions within a questionnaire."""

    section_id: str
    section_name: str
    section_description: str | None = None
    condition: Mapping[str, Any] | None = None
    _questions: list[QuestionnaireQuestion] = field(
        init=False, default_factory=list, repr=False
    )

    def __post_init__(self) -> None:
        for field_name, value in (
            ("section_id", self.section_id),
            ("section_name", self.section_name),
        ):
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")
            if not value:
                raise ValueError(f"{field_name} must be a non-empty string")

        if self.section_description is not None and not isinstance(
            self.section_description,
            str,
        ):
            raise TypeError("section_description must be a string if provided")
        if self.condition is not None:
            object.__setattr__(self, "condition", _normalise_condition(self.condition))

    @property
    def questions(self) -> tuple[QuestionnaireQuestion, ...]:
        return tuple(self._questions)

    def add_question(self, question: QuestionnaireQuestion) -> None:
        if not isinstance(question, QuestionnaireQuestion):
            raise TypeError("question must be an instance of QuestionnaireQuestion")

        if any(existing.question_id == question.question_id for existing in self._questions):
            raise ValueError(
                f"Question with id '{question.question_id}' already exists in section '{self.section_id}'"
            )

        self._questions.append(question)

    def get_question(self, question_id: str) -> QuestionnaireQuestion:
        for question in self._questions:
            if question.question_id == question_id:
                return question
        raise ValueError(
            f"Question with id '{question_id}' does not exist in section '{self.section_id}'"
        )

    def is_completed(self) -> bool:
        if not self._questions:
            return False
        for question in self._questions:
            if question.skipped:
                continue
            if question.value is None:
                return False
        return True

    def to_condition_mapping(self) -> Mapping[str, Any] | None:
        if self.condition is None:
            return None
        return deepcopy(self.condition)

    def to_mapping(self) -> Mapping[str, Any]:
        return {
            "section_id": self.section_id,
            "section_name": self.section_name,
            "section_description": self.section_description,
            "questions": [question.to_mapping() for question in self._questions],
            "condition": self.to_condition_mapping(),
        }


@dataclass(slots=True)
class Questionnaire:
    """Encapsulate the logic for rendering questionnaire payloads.

    Parameters
    ----------
    template:
        Optional Jinja template string used to render the questionnaire.
    schema:
        Optional JSON-serialisable mapping/sequence that should be emitted when
        a template is not supplied.  The structure is sorted before serialising
        to provide deterministic output.
    fallback_prompt:
        Human-friendly prompt used when neither ``template`` nor ``schema`` are
        provided.  Defaults to :data:`DEFAULT_QUESTIONNAIRE_PROMPT`.
    """

    template: str | None = None
    schema: Mapping[str, Any] | Sequence[Any] | None = None
    fallback_prompt: str = DEFAULT_QUESTIONNAIRE_PROMPT
    _sections: list[QuestionnaireSection] = field(
        init=False, default_factory=list, repr=False
    )

    def __post_init__(self) -> None:
        if self.template is not None and not isinstance(self.template, str):
            raise TypeError("Questionnaire template must be a string or None")

        if isinstance(self.schema, (str, bytes, bytearray)):
            raise TypeError(
                "Questionnaire schema must be a mapping or sequence, not a string"
            )

        if self.schema is not None and not isinstance(self.schema, (Mapping, Sequence)):
            raise TypeError(
                "Questionnaire schema must be a mapping or sequence, not "
                f"{type(self.schema).__name__}"
            )

        if not isinstance(self.fallback_prompt, str):
            raise TypeError("Questionnaire fallback_prompt must be a string")

    @property
    def sections(self) -> tuple[QuestionnaireSection, ...]:
        return tuple(self._sections)

    def add_section(
        self,
        *,
        section_id: str,
        section_name: str,
        section_description: str | None = None,
        condition: Mapping[str, Any] | None = None,
    ) -> QuestionnaireSection:
        section = QuestionnaireSection(
            section_id=section_id,
            section_name=section_name,
            section_description=section_description,
            condition=condition,
        )

        if any(existing.section_id == section.section_id for existing in self._sections):
            raise ValueError(f"Section with id '{section.section_id}' already exists")

        self._sections.append(section)
        return section

    def add_question(
        self,
        *,
        section_id: str,
        question_id: str,
        question_text: str,
        question_type: str = "text",
        question_options: Sequence[str] | None = None,
        skippable: bool = True,
    ) -> QuestionnaireQuestion:
        section = self._get_section_by_id(section_id)
        options = question_options if question_options is not None else ()
        question = QuestionnaireQuestion(
            question_id=question_id,
            question_text=question_text,
            question_type=question_type,
            question_options=options,
            skippable=skippable,
        )
        section.add_question(question)
        return question

    def get(self, *, question_id: str) -> QuestionnaireQuestion:
        section_id, question_key = self._split_question_id(question_id)
        section = self._get_section_by_id(section_id)
        return section.get_question(question_key)

    def set_answer(self, *, question_id: str, value: Any) -> None:
        question = self.get(question_id=question_id)
        question.set_value(value)

    def clear_question(self, *, question_id: str) -> None:
        question = self.get(question_id=question_id)
        question.clear_value()

    def skip_question(self, *, question_id: str) -> None:
        question = self.get(question_id=question_id)
        question.skip()

    def unskip_question(self, *, question_id: str) -> None:
        question = self.get(question_id=question_id)
        question.unskip()

    def get_visible_sections(self) -> list[QuestionnaireSection]:
        visibility_cache: dict[str, bool] = {}
        evaluation_stack: set[str] = set()

        def resolve(section: QuestionnaireSection) -> bool:
            if section.section_id in visibility_cache:
                return visibility_cache[section.section_id]
            if section.section_id in evaluation_stack:
                # Prevent circular visibility rules from crashing the resolver.
                return False
            evaluation_stack.add(section.section_id)
            condition = section.condition
            if condition is None:
                result = True
            else:
                result = self._evaluate_condition(
                    condition,
                    resolve,
                    visibility_cache,
                    evaluation_stack,
                )
            visibility_cache[section.section_id] = result
            evaluation_stack.remove(section.section_id)
            return result

        visible: list[QuestionnaireSection] = []
        for section in self._sections:
            if resolve(section):
                visible.append(section)
        return visible

    def render(self, state: Mapping[str, Any] | None = None) -> str | None:
        """Render the questionnaire payload for the supplied ``state``."""

        state_snapshot = _snapshot_state(state)

        questionnaire_payload = self._questionnaire_payload()

        if isinstance(self.template, str):
            stripped_template = self.template.strip()
            if not stripped_template:
                return None

            try:
                template = Template(self.template)
                rendered = template.render(
                    state=state_snapshot,
                    questionnaire=questionnaire_payload,
                )
            except TemplateError as exc:  # pragma: no cover - defensive guard
                raise RuntimeError("Failed to render questionnaire template") from exc

            stripped_render = rendered.strip()
            return stripped_render or None

        if questionnaire_payload is not None:
            try:
                return json.dumps(questionnaire_payload, sort_keys=True)
            except TypeError as exc:  # pragma: no cover - defensive guard
                raise RuntimeError("Questionnaire schema is not JSON serialisable") from exc

        prompt = self.fallback_prompt.strip()
        if not prompt:
            return None

        agent_name = state_snapshot.get("agent_name", "our team")
        branch_name = state_snapshot.get("branch_name", "our branch")
        return f"{prompt} Agent: {agent_name}, Branch: {branch_name}."

    def _questionnaire_payload(self) -> Mapping[str, Any] | Sequence[Any] | None:
        if self.schema is not None:
            return self.schema

        if self._sections:
            return {
                "sections": [section.to_mapping() for section in self._sections],
            }

        return None

    def _get_section_by_id(self, section_id: str) -> QuestionnaireSection:
        for section in self._sections:
            if section.section_id == section_id:
                return section
        raise ValueError(f"Section with id '{section_id}' does not exist")

    def _split_question_id(self, question_id: str) -> tuple[str, str]:
        if not isinstance(question_id, str):
            raise TypeError("question_id must be a string")
        if "." not in question_id:
            raise ValueError(
                "question_id must be in the format '<section_id>.<question_id>'"
            )
        section_id, question_key = question_id.split(".", 1)
        if not section_id or not question_key:
            raise ValueError(
                "question_id must be in the format '<section_id>.<question_id>'"
            )
        return section_id, question_key

    def _evaluate_condition(
        self,
        condition: Mapping[str, Any],
        resolver: Callable[[QuestionnaireSection], bool],
        visibility_cache: dict[str, bool],
        evaluation_stack: set[str],
    ) -> bool:
        operator = condition.get("operator")
        if not isinstance(operator, str):
            raise ValueError("Condition operator must be a string")
        op = operator.upper()

        if op in {"AND", "OR"}:
            conditions = condition.get("conditions")
            if not isinstance(conditions, Iterable) or isinstance(conditions, (str, bytes)):
                raise TypeError("conditions must be a non-empty iterable of conditions")
            evaluated = [
                self._evaluate_condition(sub, resolver, visibility_cache, evaluation_stack)
                for sub in conditions
            ]
            if not evaluated:
                return False
            return all(evaluated) if op == "AND" else any(evaluated)

        if op == "NOT":
            sub_condition = condition.get("condition")
            if not isinstance(sub_condition, Mapping):
                raise TypeError("NOT operator requires a 'condition' mapping")
            return not self._evaluate_condition(
                sub_condition,
                resolver,
                visibility_cache,
                evaluation_stack,
            )

        if op == "VISIBLE":
            section_id = condition.get("section_id")
            if not isinstance(section_id, str) or not section_id:
                raise ValueError("VISIBLE operator requires a non-empty 'section_id'")
            referenced = self._get_section_by_id(section_id)
            return resolver(referenced)

        if op == "COMPLETED":
            section_id = condition.get("section_id")
            if not isinstance(section_id, str) or not section_id:
                raise ValueError("COMPLETED operator requires a non-empty 'section_id'")
            return self._get_section_by_id(section_id).is_completed()

        if op == "ALWAYS":
            value = condition.get("value", True)
            if not isinstance(value, bool):
                raise TypeError("ALWAYS operator requires a boolean 'value'")
            return value

        raise ValueError(f"Unsupported condition operator '{operator}'")


def _normalise_condition(condition: Mapping[str, Any]) -> Mapping[str, Any]:
    normalised = deepcopy(condition)
    if not isinstance(normalised, Mapping):
        raise TypeError("condition must be a mapping")

    def _normalise(node: Mapping[str, Any]) -> Mapping[str, Any]:
        if "operator" not in node:
            raise ValueError("condition must include an 'operator'")
        operator = node["operator"]
        if not isinstance(operator, str) or not operator:
            raise ValueError("operator must be a non-empty string")
        op = operator.upper()

        if op in {"AND", "OR"}:
            conditions = node.get("conditions")
            if not isinstance(conditions, Sequence) or isinstance(conditions, (str, bytes)):
                raise TypeError(f"{op} operator requires a sequence of conditions")
            if not conditions:
                raise ValueError(f"{op} operator requires at least one condition")
            return {
                "operator": op,
                "conditions": [
                    _normalise(_ensure_mapping(sub, f"{op} condition"))
                    for sub in conditions
                ],
            }

        if op == "NOT":
            sub_condition = node.get("condition")
            return {
                "operator": op,
                "condition": _normalise(_ensure_mapping(sub_condition, "NOT condition")),
            }

        if op in {"VISIBLE", "COMPLETED"}:
            section_id = node.get("section_id")
            if not isinstance(section_id, str) or not section_id:
                raise ValueError(f"{op} operator requires a non-empty 'section_id'")
            return {"operator": op, "section_id": section_id}

        if op == "ALWAYS":
            value = node.get("value", True)
            if not isinstance(value, bool):
                raise TypeError("ALWAYS operator requires a boolean 'value'")
            return {"operator": op, "value": value}

        raise ValueError(f"Unsupported condition operator '{operator}'")

    def _ensure_mapping(value: Any, label: str) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            raise TypeError(f"{label} must be a mapping")
        return value

    return _normalise(normalised)


