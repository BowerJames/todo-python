from realtime_agent.scaffolding import QuestionnaireAgentScaffolding


def test_build_questionnaire_caches_default_prompt() -> None:
    scaffolding = QuestionnaireAgentScaffolding()
    state = {"agent_name": "Agent Smith", "branch_name": "Downtown"}

    built = scaffolding.build_questionnaire(state)

    assert built is not None
    assert "Agent: Agent Smith" in built
    assert "Branch: Downtown" in built
    assert scaffolding.render_questionnaire() == built


def test_render_questionnaire_recomputes_when_state_changes() -> None:
    scaffolding = QuestionnaireAgentScaffolding(
        questionnaire_template="Welcome {{ state.branch_name }}"
    )
    state = {"branch_name": "Central"}

    first_render = scaffolding.build_questionnaire(state)
    assert first_render == "Welcome Central"

    state["branch_name"] = "Uptown"
    assert scaffolding.render_questionnaire(state) == "Welcome Uptown"

