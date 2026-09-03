"""Prompt defaults and independent panel-agent override tests."""

from app.services.prompt_service import DEFAULT_PROMPTS, list_prompts, reset_prompt, save_prompt


def test_panel_agents_have_five_separate_default_prompts(test_session_factory):
    prompts = {item.agent: item for item in list_prompts()}
    for index in range(1, 6):
        name = f"planner_{index}"
        assert prompts[name].prompt == DEFAULT_PROMPTS[name]
        assert prompts[name].is_custom is False


def test_panel_agent_prompt_overrides_are_independent(test_session_factory):
    saved = save_prompt("planner_4", "Custom responsiveness instructions")
    prompts = {item.agent: item for item in list_prompts()}
    assert saved.is_custom is True
    assert prompts["planner_4"].prompt == "Custom responsiveness instructions"
    assert prompts["planner_3"].prompt == DEFAULT_PROMPTS["planner_3"]
    restored = reset_prompt("planner_4")
    assert restored.prompt == DEFAULT_PROMPTS["planner_4"]
    assert restored.is_custom is False
