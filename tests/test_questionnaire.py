import json

import pytest

from realtime_agent.questionnaire import (
    DEFAULT_QUESTIONNAIRE_PROMPT,
    Questionnaire,
    QuestionnaireQuestion,
    QuestionnaireSection,
    _normalise_condition,
)


def test_questionnaire_default_renders_with_fallback():
    questionnaire = Questionnaire()
    rendered = questionnaire.render({"agent_name": "HQ Agent", "branch_name": "HQ"})
    expected = (
        f"{DEFAULT_QUESTIONNAIRE_PROMPT} Agent: HQ Agent, Branch: HQ."
    )
    assert rendered == expected


def test_questionnaire_template_renders_state_and_schema():
    questionnaire = Questionnaire(
        template="Hello {{ state.agent_name }} - {{ questionnaire['title'] }}",
        schema={"title": "Customer Intake"},
    )
    rendered = questionnaire.render({"agent_name": "Support"})
    assert rendered == "Hello Support - Customer Intake"


def test_questionnaire_blank_template_returns_none():
    questionnaire = Questionnaire(template="   ")
    assert questionnaire.render({"agent_name": "Support"}) is None


def test_questionnaire_schema_serialises_stably():
    questionnaire = Questionnaire(
        schema={"b": 2, "a": 1},
    )
    rendered = questionnaire.render()
    assert json.loads(rendered) == {"a": 1, "b": 2}


def test_questionnaire_rejects_invalid_schema_type():
    with pytest.raises(TypeError):
        Questionnaire(schema="not-a-schema")


def test_questionnaire_blank_fallback_returns_none():
    questionnaire = Questionnaire(fallback_prompt="   ")
    assert questionnaire.render({"agent_name": "Support"}) is None


def test_questionnaire_question_validation_and_ops():
    question = QuestionnaireQuestion(
        question_id="intro.name",
        question_text="What is your name?",
        question_type="text",
        question_options=("Alice", "Bob"),
    )

    # options are copied to an independent list
    assert question.question_options == ["Alice", "Bob"]
    question.set_value("Alice")
    assert question.value == "Alice"
    question.clear_value()
    assert question.value is None and question.skipped is False

    question.skip()
    assert question.skipped is True and question.value is None
    question.unskip()
    assert question.skipped is False

    with pytest.raises(ValueError):
        QuestionnaireQuestion(question_id="", question_text="x")

    with pytest.raises(TypeError):
        QuestionnaireQuestion(question_id="q", question_text="x", question_options="bad")  # type: ignore[arg-type]

    non_skippable = QuestionnaireQuestion(
        question_id="q2",
        question_text="?",
        skippable=False,
    )
    with pytest.raises(ValueError):
        non_skippable.skip()


def test_questionnaire_question_options_are_case_insensitive():
    question = QuestionnaireQuestion(
        question_id="intro.choice",
        question_text="Choose one",
        question_options=("Yes", "No"),
    )

    question.set_value("YES")
    assert question.value == "Yes"

    question.set_value("no")
    assert question.value == "No"

    with pytest.raises(ValueError):
        question.set_value("maybe")


def test_questionnaire_spelling_sensitive_enforces_character_sequence():
    question = QuestionnaireQuestion(
        question_id="contact.email",
        question_text="Please provide the caller's email address",
        spelling_sensitive=True,
    )

    question.set_value(list("test@example.com"))
    assert question.value == "test@example.com"

    with pytest.raises(ValueError):
        question.set_value("test@example.com")

    with pytest.raises(ValueError):
        question.set_value(["te"])  # type: ignore[list-item]

    with pytest.raises(TypeError):
        question.set_value([1, 2, 3])  # type: ignore[list-item]


def test_questionnaire_add_question_respects_spelling_sensitive_flag():
    questionnaire = Questionnaire()
    questionnaire.add_section(section_id="contact", section_name="Contact")

    question = questionnaire.add_question(
        section_id="contact",
        question_id="email",
        question_text="What is the caller's email address?",
        question_type="text",
        spelling_sensitive=True,
    )

    assert question.spelling_sensitive is True

    with pytest.raises(ValueError):
        questionnaire.set_answer(question_id="contact.email", value="test@example.com")

    questionnaire.set_answer(
        question_id="contact.email",
        value=list("test@example.com"),
    )
    stored = questionnaire.get(question_id="contact.email")
    assert stored.value == "test@example.com"

    other = questionnaire.add_question(
        section_id="contact",
        question_id="phone",
        question_text="What is the caller's phone number?",
        question_type="text",
    )

    assert other.spelling_sensitive is False
    questionnaire.set_answer(question_id="contact.phone", value="0123456789")
    assert questionnaire.get(question_id="contact.phone").value == "0123456789"


def test_questionnaire_section_condition_and_completion():
    section = QuestionnaireSection(
        section_id="details",
        section_name="Details",
        section_description="Tell us more",
        condition={"operator": "visible", "section_id": "intro"},
    )

    question = QuestionnaireQuestion(question_id="name", question_text="Name?")
    section.add_question(question)
    assert section.to_mapping()["condition"] == {"operator": "VISIBLE", "section_id": "intro"}

    assert section.is_completed() is False
    question.set_value("Alice")
    assert section.is_completed() is True

    section.add_question(
        QuestionnaireQuestion(question_id="nickname", question_text="Nickname?", skippable=True)
    )
    with pytest.raises(ValueError):
        section.add_question(QuestionnaireQuestion(question_id="nickname", question_text="Duplicate?"))

    section.get_question("nickname").skip()
    assert section.is_completed() is True

    with pytest.raises(ValueError):
        section.get_question("missing")


def test_questionnaire_add_and_answer_questions():
    questionnaire = Questionnaire()
    section = questionnaire.add_section(section_id="intro", section_name="Intro")
    questionnaire.add_question(
        section_id="intro", question_id="name", question_text="Your name?"
    )

    question = questionnaire.get(question_id="intro.name")
    assert question.question_text == "Your name?"

    questionnaire.set_answer(question_id="intro.name", value="Alice")
    assert questionnaire.get(question_id="intro.name").value == "Alice"

    questionnaire.clear_question(question_id="intro.name")
    assert questionnaire.get(question_id="intro.name").value is None

    questionnaire.skip_question(question_id="intro.name")
    assert questionnaire.get(question_id="intro.name").skipped is True

    questionnaire.unskip_question(question_id="intro.name")
    assert questionnaire.get(question_id="intro.name").skipped is False

    with pytest.raises(ValueError):
        questionnaire.add_section(section_id="intro", section_name="Duplicate")

    with pytest.raises(ValueError):
        questionnaire.get(question_id="intro.unknown")


def test_questionnaire_get_visible_sections_conditions_and_cycles():
    questionnaire = Questionnaire()
    intro = questionnaire.add_section(section_id="intro", section_name="Intro")
    details = questionnaire.add_section(
        section_id="details",
        section_name="Details",
        condition={"operator": "VISIBLE", "section_id": "intro"},
    )
    wrap_up = questionnaire.add_section(
        section_id="wrap",
        section_name="Wrap",
        condition={
            "operator": "AND",
            "conditions": [
                {"operator": "COMPLETED", "section_id": "details"},
                {"operator": "ALWAYS", "value": True},
            ],
        },
    )
    cyclic = questionnaire.add_section(
        section_id="cycle",
        section_name="Cycle",
        condition={"operator": "VISIBLE", "section_id": "cycle"},
    )

    intro_question = QuestionnaireQuestion(question_id="name", question_text="Name?")
    intro.add_question(intro_question)

    details_question = QuestionnaireQuestion(question_id="age", question_text="Age?")
    details.add_question(details_question)

    # Without answers wrap is hidden but intro and details are visible
    visible_ids = [section.section_id for section in questionnaire.get_visible_sections()]
    assert set(visible_ids) == {"intro", "details"}

    intro_question.set_value("Alice")
    details_question.set_value(30)
    visible_ids = [section.section_id for section in questionnaire.get_visible_sections()]
    assert set(visible_ids) == {"intro", "details", "wrap"}

    # Circular visibility should resolve to False
    assert "cycle" not in visible_ids


def test_questionnaire_split_question_id_validation():
    questionnaire = Questionnaire()
    with pytest.raises(TypeError):
        questionnaire._split_question_id(10)  # type: ignore[arg-type]

    with pytest.raises(ValueError):
        questionnaire._split_question_id("invalid")

    with pytest.raises(ValueError):
        questionnaire._split_question_id(".missing")

    assert questionnaire._split_question_id("intro.name") == ("intro", "name")


def test_questionnaire_evaluate_condition_errors():
    questionnaire = Questionnaire()
    section = questionnaire.add_section(section_id="intro", section_name="Intro")

    with pytest.raises(ValueError):
        questionnaire._evaluate_condition({}, lambda _: True, {}, set())

    with pytest.raises(TypeError):
        questionnaire._evaluate_condition(
            {"operator": "AND", "conditions": "bad"},  # type: ignore[arg-type]
            lambda _: True,
            {},
            set(),
        )

    with pytest.raises(TypeError):
        questionnaire._evaluate_condition(
            {"operator": "NOT", "condition": "bad"},  # type: ignore[arg-type]
            lambda _: True,
            {},
            set(),
        )

    with pytest.raises(ValueError):
        questionnaire._evaluate_condition(
            {"operator": "VISIBLE", "section_id": ""},
            lambda _: True,
            {},
            set(),
        )

    with pytest.raises(ValueError):
        questionnaire._evaluate_condition(
            {"operator": "COMPLETED", "section_id": ""},
            lambda _: True,
            {},
            set(),
        )

    with pytest.raises(TypeError):
        questionnaire._evaluate_condition(
            {"operator": "ALWAYS", "value": "yes"},  # type: ignore[arg-type]
            lambda _: True,
            {},
            set(),
        )

    with pytest.raises(ValueError):
        questionnaire._evaluate_condition(
            {"operator": "UNKNOWN"},
            lambda _: True,
            {},
            set(),
        )

    # Valid evaluation path (AND with nested NOT and VISIBLE/COMPLETED)
    other = questionnaire.add_section(section_id="other", section_name="Other")
    other.add_question(QuestionnaireQuestion(question_id="q", question_text="?"))
    condition = {
        "operator": "AND",
        "conditions": [
            {"operator": "NOT", "condition": {"operator": "ALWAYS", "value": False}},
            {"operator": "VISIBLE", "section_id": "intro"},
            {"operator": "COMPLETED", "section_id": "other"},
        ],
    }

    def resolver(section_obj: QuestionnaireSection) -> bool:
        return section_obj.section_id == "intro"

    assert questionnaire._evaluate_condition(condition, resolver, {}, set()) is False
    other.get_question("q").set_value("done")
    assert questionnaire._evaluate_condition(condition, resolver, {}, set()) is True


def test_normalise_condition_rewrites_and_validates():
    normalised = _normalise_condition(
        {
            "operator": "and",
            "conditions": [
                {"operator": "VISIBLE", "section_id": "intro"},
                {"operator": "not", "condition": {"operator": "ALWAYS", "value": False}},
            ],
        }
    )
    assert normalised == {
        "operator": "AND",
        "conditions": [
            {"operator": "VISIBLE", "section_id": "intro"},
            {"operator": "NOT", "condition": {"operator": "ALWAYS", "value": False}},
        ],
    }

    with pytest.raises(ValueError):
        _normalise_condition({"operator": "AND", "conditions": []})

    with pytest.raises(TypeError):
        _normalise_condition({"operator": "ALWAYS", "value": "yes"})  # type: ignore[arg-type]

    with pytest.raises(ValueError):
        _normalise_condition({"operator": "VISIBLE", "section_id": ""})


def test_questionnaire_from_config_builds_complete_questionnaire():
    config = {
        "sections": [
            {
                "section_id": "intro",
                "section_name": "Introduction",
                "section_description": "Please answer these questions",
                "questions": [
                    {
                        "question_id": "name",
                        "question_text": "What is your name?",
                        "question_type": "text",
                        "question_options": ["Alice", "Bob"],
                        "skippable": False,
                        "spelling_sensitive": False,
                    },
                    {
                        "question_id": "age",
                        "question_text": "What is your age?",
                        "question_type": "text",
                        "skippable": True,
                    },
                ],
            },
            {
                "section_id": "details",
                "section_name": "Details",
                "section_description": "More information",
                "condition": {"operator": "COMPLETED", "section_id": "intro"},
                "questions": [
                    {
                        "question_id": "email",
                        "question_text": "What is your email?",
                        "question_type": "text",
                        "spelling_sensitive": True,
                    },
                ],
            },
        ],
    }

    questionnaire = Questionnaire.from_config(config)

    assert len(questionnaire.sections) == 2

    intro_section = questionnaire.sections[0]
    assert intro_section.section_id == "intro"
    assert intro_section.section_name == "Introduction"
    assert intro_section.section_description == "Please answer these questions"
    assert intro_section.condition is None
    assert len(intro_section.questions) == 2

    name_question = intro_section.questions[0]
    assert name_question.question_id == "name"
    assert name_question.question_text == "What is your name?"
    assert name_question.question_type == "text"
    assert name_question.question_options == ["Alice", "Bob"]
    assert name_question.skippable is False
    assert name_question.spelling_sensitive is False

    age_question = intro_section.questions[1]
    assert age_question.question_id == "age"
    assert age_question.question_text == "What is your age?"
    assert age_question.question_type == "text"
    assert age_question.question_options is None
    assert age_question.skippable is True
    assert age_question.spelling_sensitive is False

    details_section = questionnaire.sections[1]
    assert details_section.section_id == "details"
    assert details_section.section_name == "Details"
    assert details_section.section_description == "More information"
    assert details_section.condition == {"operator": "COMPLETED", "section_id": "intro"}
    assert len(details_section.questions) == 1

    email_question = details_section.questions[0]
    assert email_question.question_id == "email"
    assert email_question.question_text == "What is your email?"
    assert email_question.question_type == "text"
    assert email_question.question_options is None
    assert email_question.skippable is True
    assert email_question.spelling_sensitive is True


def test_questionnaire_from_config_rejects_invalid_config_type():
    with pytest.raises(TypeError):
        Questionnaire.from_config("not a dict")  # type: ignore[arg-type]


def test_questionnaire_from_config_requires_sections_key():
    with pytest.raises(TypeError):
        Questionnaire.from_config({})


def test_questionnaire_from_config_requires_sections_to_be_sequence():
    with pytest.raises(TypeError):
        Questionnaire.from_config({"sections": "not a sequence"})  # type: ignore[dict-item]


def test_questionnaire_from_config_requires_section_to_be_mapping():
    with pytest.raises(TypeError):
        Questionnaire.from_config({"sections": ["not a dict"]})


def test_questionnaire_from_config_requires_section_id():
    with pytest.raises(TypeError):
        Questionnaire.from_config({"sections": [{"section_name": "Test"}]})


def test_questionnaire_from_config_requires_section_name():
    with pytest.raises(TypeError):
        Questionnaire.from_config({"sections": [{"section_id": "test"}]})


def test_questionnaire_from_config_requires_questions_to_be_sequence():
    with pytest.raises(TypeError):
        Questionnaire.from_config(
            {
                "sections": [
                    {
                        "section_id": "test",
                        "section_name": "Test",
                        "questions": "not a sequence",  # type: ignore[dict-item]
                    }
                ]
            }
        )


def test_questionnaire_from_config_requires_question_to_be_mapping():
    with pytest.raises(TypeError):
        Questionnaire.from_config(
            {
                "sections": [
                    {
                        "section_id": "test",
                        "section_name": "Test",
                        "questions": ["not a dict"],
                    }
                ]
            }
        )


def test_questionnaire_from_config_requires_question_id():
    with pytest.raises(TypeError):
        Questionnaire.from_config(
            {
                "sections": [
                    {
                        "section_id": "test",
                        "section_name": "Test",
                        "questions": [{"question_text": "Test?"}],
                    }
                ]
            }
        )


def test_questionnaire_from_config_requires_question_text():
    with pytest.raises(TypeError):
        Questionnaire.from_config(
            {
                "sections": [
                    {
                        "section_id": "test",
                        "section_name": "Test",
                        "questions": [{"question_id": "q1"}],
                    }
                ]
            }
        )


def test_questionnaire_from_config_handles_empty_sections():
    config = {"sections": []}
    questionnaire = Questionnaire.from_config(config)
    assert len(questionnaire.sections) == 0


def test_questionnaire_from_config_handles_section_without_questions():
    config = {
        "sections": [
            {
                "section_id": "test",
                "section_name": "Test",
            }
        ]
    }
    questionnaire = Questionnaire.from_config(config)
    assert len(questionnaire.sections) == 1
    assert len(questionnaire.sections[0].questions) == 0

