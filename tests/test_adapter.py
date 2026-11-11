from rca.adapters.whoandwhen import Turn, build_run, extract_turns, normalize_agent, parse_example


def turns():
    return [
        Turn(index=0, agent="A", content="a0"),
        Turn(index=1, agent="A", content="a1"),
        Turn(index=2, agent="B", content="b0"),
        Turn(index=3, agent="A", content="a2"),
    ]


def test_contiguous_messages_group_into_stages_with_attempts():
    run = build_run("r1", task="solve it", turns=turns())
    assert [(s.name, s.index, s.attempt) for s in run.ordered_stages()] == [
        ("A", 0, 1),
        ("B", 1, 1),
        ("A", 2, 2),
    ]


def test_step_indices_match_history_indices():
    run = build_run("r1", task="solve it", turns=turns())
    s0, s1, s2 = run.ordered_stages()
    assert [s.index for s in run.steps_for(s0.id)] == [0, 1]
    assert [s.index for s in run.steps_for(s1.id)] == [2]
    assert [s.index for s in run.steps_for(s2.id)] == [3]


def test_handoffs_carry_task_and_boundary_message():
    run = build_run("r1", task="solve it", turns=turns())
    s0, s1, s2 = run.ordered_stages()
    first = run.inbound(s0.id)
    assert first.from_stage is None and first.payload == "Task: solve it"
    into_b = run.inbound(s1.id)
    assert into_b.from_stage == s0.id
    assert "a1" in into_b.payload and "solve it" in into_b.payload
    final = run.outbound(s2.id)
    assert final.to_stage is None and final.payload == "a2"


def test_empty_history_yields_no_stages():
    run = build_run("r1", task="t", turns=[])
    assert run.stages == [] and run.steps == []


def test_normalize_agent_strips_orchestrator_variants():
    assert normalize_agent("Orchestrator (thought)") == "Orchestrator"
    assert normalize_agent("Orchestrator (-> WebSurfer)") == "Orchestrator"
    assert normalize_agent("WebSurfer") == "WebSurfer"


def test_parse_example_filters_human_and_preserves_indices():
    example = {
        "question": "q",
        "history": [
            {"role": "human", "content": "the task"},
            {"role": "Orchestrator (thought)", "content": "think"},
            {"role": "Orchestrator (-> WebSurfer)", "content": "go fetch"},
            {"role": "WebSurfer", "content": "page content"},
        ],
        "mistake_agent": "Orchestrator",
        "mistake_step": "2",
        "mistake_reason": "bad delegation",
    }
    run, truth = parse_example(example, "r1")
    orchestrator, websurfer = run.ordered_stages()
    assert orchestrator.name == "Orchestrator"  # variants collapse into one stage
    assert [s.index for s in run.steps_for(orchestrator.id)] == [1, 2]  # human kept index 0
    assert websurfer.name == "WebSurfer"
    assert truth.mistake_agent == "Orchestrator"
    assert truth.mistake_step == 2


def test_extract_turns_uses_name_when_present():
    example = {
        "history": [
            {"name": "Verification_Expert", "role": "assistant", "content": "checking"},
        ]
    }
    (turn,) = extract_turns(example)
    assert turn.agent == "Verification_Expert"
