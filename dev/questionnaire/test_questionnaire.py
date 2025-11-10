import pytest

from realtime_agent.questionnaire import Questionnaire

def test_questionnaire_builds():
    questionnaire = Questionnaire()

def test_questionnaire_can_add_section(questionnaire: Questionnaire, add_section_1):
    assert len(questionnaire.sections) == 1


def test_questionnaire_added_section_details_are_correct(questionnaire: Questionnaire, add_section_1, section_1):
    assert len(questionnaire.sections) == 1
    assert questionnaire.sections[0].section_id == section_1["section_id"]
    assert questionnaire.sections[0].section_name == section_1["section_name"]
    assert questionnaire.sections[0].section_description == section_1["section_description"]

def test_cannot_add_question_without_section(questionnaire: Questionnaire, question_1_1):
    try:
        questionnaire.add_question(
            **question_1_1,
        )
        pytest.fail("Expected subclass of ValueError, but no exception was raised")
    except Exception as e:
        assert issubclass(type(e), ValueError)
    

def test_questionnaire_can_add_question(questionnaire: Questionnaire, add_section_1, add_question_1_1):
    pass

def test_added_questions_default_to_none(questionnaire: Questionnaire, add_section_1, add_question_1_1, section_1, question_1_1):
    question = questionnaire.get(
        question_id=".".join([section_1["section_id"], question_1_1["question_id"]]),
    )
    assert question.value is None

def test_added_questions_default_to_not_skipped(questionnaire: Questionnaire, add_section_1, add_question_1_1, section_1, question_1_1):
    question = questionnaire.get(
        question_id=".".join([section_1["section_id"], question_1_1["question_id"]]),
    )
    assert not question.skipped

def test_can_answer_question(questionnaire: Questionnaire, add_section_1, add_question_1_1, section_1, question_1_1):
    questionnaire.set_answer(
        question_id=".".join([section_1["section_id"], question_1_1["question_id"]]),
        value="Yes",
    )

def test_can_overwrite_answer(questionnaire: Questionnaire, add_section_1, add_question_1_1, section_1, question_1_1):
    questionnaire.set_answer(
        question_id=".".join([section_1["section_id"], question_1_1["question_id"]]),
        value="Yes",
    )
    questionnaire.set_answer(
        question_id=".".join([section_1["section_id"], question_1_1["question_id"]]),
        value="No",
    )
    question = questionnaire.get(
        question_id=".".join([section_1["section_id"], question_1_1["question_id"]]),
    )
    assert question.value == "No"

def test_answered_question_updates_value(questionnaire: Questionnaire, add_section_1, add_question_1_1, section_1, question_1_1):
    questionnaire.set_answer(
        question_id=".".join([section_1["section_id"], question_1_1["question_id"]]),
        value="Yes",
    )
    question = questionnaire.get(
        question_id=".".join([section_1["section_id"], question_1_1["question_id"]]),
    )
    assert question.value == "Yes"

def test_cannot_set_answer_when_not_option(questionnaire: Questionnaire, add_section_1, add_question_1_1, section_1, question_1_1):
    try:
        questionnaire.set_answer(
            question_id=".".join([section_1["section_id"], question_1_1["question_id"]]),
            value="Not an option",
        )
        pytest.fail("Expected subclass of ValueError, but no exception was raised")
    except Exception as e:
        assert issubclass(type(e), Exception)

def test_set_answer_with_options_is_case_insensitive(questionnaire: Questionnaire, add_section_1, add_question_1_1, section_1, question_1_1):
    questionnaire.set_answer(
        question_id=".".join([section_1["section_id"], question_1_1["question_id"]]),
        value="YES",
    )
    question = questionnaire.get(
        question_id=".".join([section_1["section_id"], question_1_1["question_id"]]),
    )
    assert question.value == "Yes"


def test_questionnaire_added_question_details_are_correct(questionnaire: Questionnaire, add_section_1, add_question_1_1, question_1_1):
    section = next(section for section in questionnaire.sections if section.section_id == question_1_1["section_id"])
    assert len(section.questions) == 1
    assert section.questions[0].question_id == question_1_1["question_id"]
    assert section.questions[0].question_text == question_1_1["question_text"]
    assert section.questions[0].question_type == question_1_1["question_type"]
    assert section.questions[0].question_options == question_1_1["question_options"]
    assert section.questions[0].skippable == question_1_1["skippable"]

def test_can_add_multiple_questions_to_section(questionnaire: Questionnaire, add_section_1, add_question_1_1, add_question_1_2):
    pass

def test_can_add_multiple_sections(questionnaire: Questionnaire, add_section_1, add_section_2):
    pass

def test_visible_sections_are_visible(questionnaire: Questionnaire, add_section_1_with_questions, add_section_2, section_1, section_2):
    visible_sections = questionnaire.get_visible_sections()
    assert len(visible_sections) == 1

    only_visible_section = visible_sections[0]
    assert only_visible_section.section_id == section_1["section_id"]
    assert only_visible_section.section_name == section_1["section_name"]
    assert only_visible_section.section_description == section_1["section_description"]

def test_section_2_becomes_visible_when_section_1_is_completed(questionnaire: Questionnaire, add_section_1_with_questions, add_section_2_with_questions, section_1, section_2):
    section_1 = next(section for section in questionnaire.sections if section.section_id == section_1["section_id"])
    for question in section_1.questions:
        questionnaire.set_answer(
            question_id=".".join([section_1.section_id, question.question_id]),
            value="Yes",
        )
    
    visible_sections = questionnaire.get_visible_sections()
    assert len(visible_sections) == 2
    assert section_2["section_id"] in [section.section_id for section in visible_sections]

def test_spelling_sensitive_questions_accepts_list_of_chars(questionnaire: Questionnaire, add_section_1_with_questions, add_section_2_with_questions, section_1, section_2, question_2_3):
    section_1_section = next(section for section in questionnaire.sections if section.section_id == section_1["section_id"])
    for question in section_1_section.questions:
        questionnaire.set_answer(
            question_id=".".join([section_1_section.section_id, question.question_id]),
            value="Yes",
        )
    questionnaire.set_answer(
        question_id=".".join([section_2["section_id"], question_2_3["question_id"]]),
        value=[
            'j',
            'a',
            'm',
            'e',
            's',
            '@',
            't',
            'e',
            's',
            't',
            '.',
            'c',
            'o',
            'm',
        ],
    )
    question = questionnaire.get(
        question_id=".".join([section_2["section_id"], question_2_3["question_id"]]),
    )
    assert question.value == "james@test.com"

def test_spelling_sensitive_requires_list_of_chars(questionnaire: Questionnaire, add_section_1_with_questions, add_section_2_with_questions, section_1, section_2, question_2_3):
    section_1_section = next(section for section in questionnaire.sections if section.section_id == section_1["section_id"])
    for question in section_1_section.questions:
        questionnaire.set_answer(
            question_id=".".join([section_1_section.section_id, question.question_id]),
            value="Yes",
        )
    try:
        questionnaire.set_answer(
            question_id=".".join([section_2["section_id"], question_2_3["question_id"]]),
            value="james@test.com",
        )
        pytest.fail("Expected subclass of ValueError, but no exception was raised")
    except Exception as e:
        assert issubclass(type(e), Exception)




