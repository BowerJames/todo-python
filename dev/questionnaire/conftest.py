import pytest

from realtime_agent.questionnaire import Questionnaire

@pytest.fixture
def questionnaire():
    return Questionnaire()

@pytest.fixture
def section_1():
    return {
        "section_id": "1",
        "section_name": "Purpose of Call",
        "section_description": "To start the conversation, please answer the following questions to determine the core purpose of the call.",
    }

@pytest.fixture
def question_1_1():
    return {
        "section_id": "1",
        "question_id": "1",
        "question_text": "Is the caller calling to book a viewing (Yes/No)?",
        "question_type": "text",
        "question_options": ["Yes", "No"],
        "skippable": False,
    }

@pytest.fixture
def question_1_2():
    return {
        "section_id": "1",
        "question_id": "2",
        "question_text": "Is the caller calling to book a valuation (Yes/No)?",
        "question_type": "text",
        "question_options": ["Yes", "No"],
        "skippable": False,
    }

@pytest.fixture
def question_1_3():
    return {
        "section_id": "1",
        "question_id": "3",
        "question_text": "Is the caller calling to ask for mortgage advice (Yes/No)?",
        "question_type": "text",
        "question_options": ["Yes", "No"],
        "skippable": False,
    }

@pytest.fixture
def section_2():
    return {
        "section_id": "2",
        "section_name": "Contact Details",
        "section_description": "Please inform the caller that to proceed you will need to collect their contact details. This is required before any viewing, valuation or mortgage advice requests can be made.",
        "condition": {
            "operator": "AND",
            "conditions": [
                {
                    "operator": "COMPLETED",
                    "section_id": "1",
                },
                {
                    "operator": "VISIBLE",
                    "section_id": "1",
                },
            ]
        }
    }

@pytest.fixture
def question_2_1():
    return {
        "section_id": "2",
        "question_id": "1",
        "question_text": "What is the caller's first name?",
        "question_type": "text",
        "skippable": False,
    }

@pytest.fixture
def question_2_2():
    return {
        "section_id": "2",
        "question_id": "2",
        "question_text": "What is the caller's last name?",
        "question_type": "text",
        "skippable": False,
    }

@pytest.fixture
def question_2_3():
    return {
        "section_id": "2",
        "question_id": "3",
        "question_text": "What is the caller's email address?",
        "question_type": "text",
        "skippable": False,
        "spelling_sensitive": True,
    }

@pytest.fixture
def question_2_4():
    return {
        "section_id": "2",
        "question_id": "4",
        "question_text": "What is the caller's phone number?",
        "question_type": "text",
        "skippable": False,
        "spelling_sensitive": True,
    }

@pytest.fixture
def add_section_1(questionnaire: Questionnaire, section_1):
    questionnaire.add_section(
        **section_1,
    )

@pytest.fixture
def add_question_1_1(questionnaire: Questionnaire, question_1_1):
    questionnaire.add_question(
        **question_1_1,
    )

@pytest.fixture
def add_question_1_2(questionnaire: Questionnaire, question_1_2):
    questionnaire.add_question(
        **question_1_2,
    )

@pytest.fixture
def add_question_1_3(questionnaire: Questionnaire, question_1_3):
    questionnaire.add_question(
        **question_1_3,
    )

@pytest.fixture
def add_section_1_with_questions(
    questionnaire,
    add_section_1,
    add_question_1_1,
    add_question_1_2,
    add_question_1_3,
):
    pass

@pytest.fixture
def add_section_2(questionnaire: Questionnaire, section_2):
    questionnaire.add_section(
        **section_2,
    )

@pytest.fixture
def add_question_2_1(questionnaire: Questionnaire, question_2_1):
    questionnaire.add_question(
        **question_2_1,
    )

@pytest.fixture
def add_question_2_2(questionnaire: Questionnaire, question_2_2):
    questionnaire.add_question(
        **question_2_2,
    )

@pytest.fixture
def add_question_2_3(questionnaire: Questionnaire, question_2_3):
    questionnaire.add_question(
        **question_2_3,
    )

@pytest.fixture
def add_section_2_with_questions(
    questionnaire,
    add_section_2,
    add_question_2_1,
    add_question_2_2,
    add_question_2_3,
):
    pass