from agents import FileSearchTool, Agent, ModelSettings, TResponseInputItem, Runner, RunConfig, trace
from openai import AsyncOpenAI
from types import SimpleNamespace
from openai.types.shared.reasoning import Reasoning
from pydantic import BaseModel
try:
  from guardrails.runtime import load_config_bundle, instantiate_guardrails, run_guardrails
  _GUARDRAILS_AVAILABLE = True
except Exception:
  load_config_bundle = instantiate_guardrails = run_guardrails = None  # type: ignore
  _GUARDRAILS_AVAILABLE = False

# Tool definitions
file_search = FileSearchTool(
  vector_store_ids=[
    "vs_68f17be16af48191a4451d421f3af3c3"
  ]
)
# Shared client for guardrails and file search
client = AsyncOpenAI()
ctx = SimpleNamespace(guardrail_llm=client) if _GUARDRAILS_AVAILABLE else None
# Guardrails definitions
guardrails_config = (
  {
    "guardrails": [
      {
        "name": "Hallucination Detection",
        "config": {
          "model": "gpt-4.1-mini",
          "knowledge_source": "vs_68f17be16af48191a4451d421f3af3c3",
          "confidence_threshold": 0.8
        }
      }
    ]
  }
) if _GUARDRAILS_AVAILABLE else None
# Guardrails utils

def guardrails_has_tripwire(results):
    return any(getattr(r, "tripwire_triggered", False) is True for r in (results or []))

def get_guardrail_checked_text(results, fallback_text):
    for r in (results or []):
        info = getattr(r, "info", None) or {}
        if isinstance(info, dict) and ("checked_text" in info):
            return info.get("checked_text") or fallback_text
    return fallback_text

def build_guardrail_fail_output(results):
    failures = []
    for r in (results or []):
        if getattr(r, "tripwire_triggered", False):
            info = getattr(r, "info", None) or {}
            failure = {
                "guardrail_name": info.get("guardrail_name"),
            }
            for key in ("flagged", "confidence", "threshold", "hallucination_type", "hallucinated_statements", "verified_statements"):
                if key in (info or {}):
                    failure[key] = info.get(key)
            failures.append(failure)
    return {"failed": len(failures) > 0, "failures": failures}


wills_requirements_analyst = Agent(
  name="Will requirements analyst",
  instructions="""You are a Will-Intake Requirements Analyst. Combine the product flow in `business_logic_phases.md` with the legal guardrails in `legal_requirements_us.md` to turn the user's prompt into a structured intake/requirements blueprint.

Context to rely on:
- `will-it/docs/business_logic_phases.md` is the canonical intake flow (Phases 0–9). Use its phase purposes, outputs, and gaps.
- `will-it/docs/legal_requirements_us.md` captures U.S. validity, execution, electronic will, and operator constraints. Prefer its language for legal requirements.
- File search contains other supporting briefs—cite snippets only when they are consistent with the two primary docs above.

Steps:
1. Restate the user problem/goal in ≤80 words.
2. Map the scenario to the highest-leverage phases (Phase 0–9). For each selected phase, capture (a) phase purpose, (b) what the prompt already provides, (c) missing data/questions, (d) decision or risk flags. Pull phrasing from `business_logic_phases.md` where helpful.
3. Extract legal requirements that apply (capacity, writing, witnesses, notarization/self-proving, electronic/remote execution, community property/elective share, non-probate coordination). Tie each item back to `legal_requirements_us.md`.
4. List concrete follow-up questions grouped as `critical`, `recommended`, or `nice_to_have`. Critical items unblock legality; recommended items improve personalization; nice_to_have adds polish.
5. Mention any execution/operational blockers (e.g., e-will availability, RON vendor duty, state-specific restrictions).

Output: return a fenced JSON object with the following shape (strings may contain markdown lists):
```json
{
  "user_summary": "",
  "phase_matrix": [
    {
      "phase": "Phase X — Name",
      "purpose": "",
      "known_inputs": [],
      "missing_information": [],
      "risks_or_decisions": []
    }
  ],
  "legal_requirements": {
    "core_validity": "",
    "execution": "",
    "jurisdictional_or_property_considerations": "",
    "non_probate_and_coordination": ""
  },
  "follow_up_questions": {
    "critical": [],
    "recommended": [],
    "nice_to_have": []
  },
  "operational_flags": []
}
```

Guidelines:
- Use specific citations like `(business_logic_phases)` or `(legal_requirements_us)` rather than bluebook cites.
- When information is unknown, state it explicitly rather than guessing.
- Keep the JSON valid and compact enough to hand to another agent; avoid prose outside the fenced block.""",
  model="gpt-5",
  tools=[
    file_search
  ],
  model_settings=ModelSettings(
    store=True,
    reasoning=Reasoning(
      effort="medium",
      summary="auto"
    )
  )
)


wills_briefing_writer = Agent(
  name="Will planning overview writer",
  instructions="""You turn the analyst JSON plus the original user ask into an actionable planning brief for a product/design teammate.

Expectations:
- Preserve factual accuracy; never invent law.
- Lean on `business_logic_phases.md` for workflow framing and `legal_requirements_us.md` for requirements. Cite them inline using `(business_logic_phases)` or `(legal_requirements_us)`.
- Highlight tensions between business logic gaps and the legal requirements (e.g., missing witnesses vs. state rule).

Steps:
1. Produce a short **Snapshot** (jurisdiction, goals, blockers).
2. Under **Phase Focus**, list the top 3–4 phases that need attention. For each: what to capture next, decisions to make, and why it matters legally.
3. Under **Legal Requirements & Execution**, summarize: capacity/writing, witness & notarization rules, e-will/remote feasibility, spousal/community-property protections, and non-probate coordination requirements.
4. Under **Action Plan**, group tasks into `Now`, `Soon`, and `Later`, referencing how they unblock the flow.
5. Under **Questions for User/Lawyer**, copy the analyst follow-ups but rewrite them as clear bullets grouped by urgency.

Formatting:
- Use markdown headings already specified. Under each heading use concise bullet lists (no tables needed).
- Reference sources with `(business_logic_phases)` or `(legal_requirements_us)` where relevant.
- Close with a one-line risk reminder if critical legal prerequisites are still unknown.""",
  model="gpt-5",
  tools=[
    file_search
  ],
  model_settings=ModelSettings(
    store=True,
    reasoning=Reasoning(
      effort="medium",
      summary="auto"
    )
  )
)


class WorkflowInput(BaseModel):
  input_as_text: str


# Main code entrypoint
async def run_workflow(workflow_input: WorkflowInput):
  with trace("Wills Intake + Law Agent"):
    state = {
      "user_request": workflow_input.input_as_text
    }
    workflow = workflow_input.model_dump()
    conversation_history: list[TResponseInputItem] = [
      {
        "role": "user",
        "content": [
          {
            "type": "input_text",
            "text": workflow["input_as_text"]
          }
        ]
      }
    ]
    analyst_result_temp = await Runner.run(
      wills_requirements_analyst,
      input=[
        *conversation_history
      ],
      run_config=RunConfig(trace_metadata={
        "__trace_source__": "agent-builder",
        "workflow_id": "wf_c748b87b5c8c4b76a1f909933d4dc9df"
      })
    )

    conversation_history.extend([item.to_input_item() for item in analyst_result_temp.new_items])
    state["requirements_blueprint"] = analyst_result_temp.final_output_as(str)

    briefing_result_temp = await Runner.run(
      wills_briefing_writer,
      input=[
        *conversation_history
      ],
      run_config=RunConfig(trace_metadata={
        "__trace_source__": "agent-builder",
        "workflow_id": "wf_c748b87b5c8c4b76a1f909933d4dc9df"
      })
    )

    conversation_history.extend([item.to_input_item() for item in briefing_result_temp.new_items])

    briefing_result = {
      "output_text": briefing_result_temp.final_output_as(str)
    }
    guardrails_inputtext = briefing_result["output_text"]
    if _GUARDRAILS_AVAILABLE and guardrails_config and ctx:
      guardrails_runner = instantiate_guardrails(load_config_bundle(guardrails_config))
      guardrails_result = await run_guardrails(ctx, guardrails_inputtext, "text/plain", guardrails_runner, suppress_tripwire=True)
      guardrails_hastripwire = guardrails_has_tripwire(guardrails_result)
      guardrails_anonymizedtext = get_guardrail_checked_text(guardrails_result, guardrails_inputtext)
      guardrails_output = (guardrails_hastripwire and build_guardrail_fail_output(guardrails_result or [])) or (guardrails_anonymizedtext or guardrails_inputtext)
      if guardrails_hastripwire:
        raise Exception(f"Guardrails tripwire triggered: {guardrails_output}")
      else:
        return guardrails_output
    return guardrails_inputtext
