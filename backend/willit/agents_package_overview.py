from agents import FileSearchTool, Agent, ModelSettings, TResponseInputItem, Runner, RunConfig, trace
from openai import AsyncOpenAI
from types import SimpleNamespace
from guardrails.runtime import load_config_bundle, instantiate_guardrails, run_guardrails
from openai.types.shared.reasoning import Reasoning
from pydantic import BaseModel

# Tool definitions
file_search = FileSearchTool(
  vector_store_ids=[
    ""
  ]
)
# Shared client for guardrails and file search
client = AsyncOpenAI()
ctx = SimpleNamespace(guardrail_llm=client)
# Guardrails definitions
guardrails_config = {
  "guardrails": [
    {
      "name": "Hallucination Detection",
      "config": {
        "model": "gpt-4.1-mini",
        "knowledge_source": "",
        "confidence_threshold": 0.8
      }
    }
  ]
}
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
rules_to_doctrinal_overview = Agent(
  name="Rules to Doctrinal overview",
  instructions="""Given a set of legal rules related to a specific case, analyze these rules step-by-step and generate a doctrinal overview that clearly synthesizes their underlying legal principles and their application to the case.

# Steps

1. Carefully read the provided legal rules for the case.
2. Identify and outline the key legal principles contained within each rule.
3. Explain how these rules interrelate, overlap, or differ.
4. Synthesize the information by reasoning through how these principles would collectively inform or resolve key doctrinal questions in the case.
5. Only after conducting this analysis, create a structured doctrinal overview that summarizes your findings and insights.

# Output Format

- Provide a concise, well-organized doctrinal overview.
- Use headings or bullet points to structure your analysis.
- Response should be in plain text and divided as follows:
    1. Analysis (explanation and synthesis steps)
    2. Doctrinal Overview (summary and conclusions)

# Example

**Analysis**
- Rule 1: [Summarize rule, state legal principle.]
- Rule 2: [Summarize rule, state legal principle.]
- Comparison/Relationship: [Explain how rules interact, support, or contradict each other.]
- Synthesis: [Reason out how the doctrines together shape the legal framework for the case.]

**Doctrinal Overview**
- Key legal principles: [Summarize]
- Application to the case: [Summarize]
(For real cases, examples will be more detailed and cite specific rules or statutes.)

# Notes

- Only produce the doctrinal overview after completing your internal analysis.
- Ensure clarity, organization, and focus on the principles’ collective application, not just listing rules independently.
- If the provided rules are ambiguous or incomplete, state your assumptions.
- Do not alter the biomarkers in any way (location or form) and be sure to use the biomarker convention to cite. """,
  model="gpt-5",
  tools=[
    file_search
  ],
  model_settings=ModelSettings(
    store=True,
    reasoning=Reasoning(
      effort="low",
      summary="auto"
    )
  )
)


conform_to_legal_writing = Agent(
  name="Conform to legal writing",
  instructions="""Revise the input document text to conform to a standard legal writing style, ensuring clarity, formality, and consistency typical of legal documents. Do not alter, move, reformat, or modify any biomarkers within the text; preserve their location, form, and content exactly as provided. Review the entire document carefully and update all other language as needed to align with legal drafting conventions.

- Carefully edit for tone, sentence structure, and word choice to match legal style, while maintaining the original meaning except where stylistic improvements are needed.
- Do not introduce new information or interpret biomarker text; handle all other document content as described.
- Confirm that no biomarkers have been moved or changed during the revision process.

**Output format:**  
Return only the revised document as plain text, matching the original document’s structure and formatting, but with legal style improvements applied.

**Example Input:**  
This Agreement is between the buyer and seller. {BIOMARKER1} The buyer agrees to purchase the assets.

**Example Output:**  
This Agreement is entered into by and between the Buyer and the Seller. {BIOMARKER1} The Buyer hereby agrees to purchase the Assets.

*(Note: Real examples will be longer and may include additional legal language; complex biomarkers must remain unchanged in both position and format.)*

**Important:**  
- The main objective is to revise the document for legal style without in any way modifying biomarkers or their placement.  
- Biomarkers are identifiers within the text—examples include {BIOMARKER1}, <<MARKER_A>>, or similar tags.  
- Any deviation from this may cause errors in downstream processing.""",
  model="gpt-5",
  model_settings=ModelSettings(
    store=True,
    reasoning=Reasoning(
      effort="low",
      summary="auto"
    )
  )
)


class WorkflowInput(BaseModel):
  input_as_text: str


# Main code entrypoint
async def run_workflow(workflow_input: WorkflowInput):
  with trace("Doctrinal Overview Agent"):
    state = {
      "revised_rules": "~~| Sub Issue: Statutory definition of “neglect” applicable to MCL 712A.2(b)(1) and (2). Rule: For purposes of child-protective jurisdiction, “neglect” means harm to a child’s health or welfare by a person responsible for the child’s health or welfare that occurs through negligent treatment, including the failure to provide adequate food, clothing, shelter, or medical care, though financially able to do so, or the failure to seek financial or other reasonable means to provide adequate food, clothing, shelter, or medical care. (biomarker: ||MCL 722.602|| e-64695679-3c0e-49b0-8e73-ab0833979053) |~~ ~~| Sub Issue: Jurisdictional ground under MCL 712A.2(b)(1): parent-based neglect, refusal, substantial risk, abandonment, or lack of proper custody/guardianship. Rule: The family division has jurisdiction over a juvenile under 18 years of age found within the county whose parent or other person legally responsible for the child, when able to do so, neglects or refuses to provide proper or necessary support, education, medical, surgical, or other care necessary for the child’s health or morals. (biomarker: ||MCL 712A.2|| e-5cea6761-bab2-4941-a6c8-adf6c5052ef4) The same subsection confers jurisdiction where the child is subject to a substantial risk of harm to his or her mental well-being, is abandoned by a parent, guardian, or other custodian, or is without proper custody or guardianship. (biomarker: ||MCL 712A.2|| e-5cea6761-bab2-4941-a6c8-adf6c5052ef4) “Neglect” in subsection (b)(1) incorporates the statutory definition in the Child Abuse and Neglect Prevention Act. (biomarker: ||MCL 712A.2|| e-6fbedc92-6651-46b2-a8b4-cdbc4ec11b2a); (biomarker: ||MCL 722.602|| e-64695679-3c0e-49b0-8e73-ab0833979053) “Education” in subsection (b)(1) means learning based on an organized educational program appropriate to the child’s age and abilities across core subject areas. (biomarker: ||MCL 712A.2|| e-46d5e552-7bad-4899-9888-2be4524d32d6) “Without proper custody or guardianship” does not include a situation in which a parent has placed the child with another legally responsible person who is able to and does provide proper care and maintenance. (biomarker: ||MCL 712A.2|| e-ad745b5a-1430-414f-a34c-d0c7c7eb37af) |~~ ~~| Sub Issue: Jurisdictional ground under MCL 712A.2(b)(2): unfit home or environment “by reason of” specified parental fault, including neglect. Rule: The family division has jurisdiction over a juvenile under 18 years of age found within the county whose home or environment, by reason of neglect, cruelty, drunkenness, criminality, or depravity on the part of a parent, guardian, nonparent adult, or other custodian, is an unfit place for the juvenile to live in. (biomarker: ||MCL 712A.2|| e-0488d0f0-04bd-4686-9be7-c25cf67256c4) As used in subsection (b)(2), “neglect” has the meaning set forth in MCL 722.602(1)(d). (biomarker: ||MCL 712A.2|| e-0488d0f0-04bd-4686-9be7-c25cf67256c4); (biomarker: ||MCL 722.602|| e-64695679-3c0e-49b0-8e73-ab0833979053) |~~ ~~| Sub Issue: Threshold jurisdictional prerequisites common to MCL 712A.2(b)(1) and (2). Rule: Both subsections (b)(1) and (b)(2) operate within the statute’s threshold requirement that the subject be a juvenile under 18 years of age who is found within the county. (biomarker: ||MCL 712A.2|| e-9334f9e9-ddaa-485e-9894-e22e47a8fec5) |~~ ~~| Main Issue: Whether the trial court should have assumed jurisdiction over the minor under MCL 712A.2(b)(1) and (2) (i.e., respondent mother’s alleged negligence or unfitness of the home), in light of appellant’s contention that mother was not negligent and the home was not unfit, and appellee’s contention that jurisdiction was proper. Standard of Review: On appeal, a trial court’s decision to exercise child-protective jurisdiction is reviewed for clear error in light of the court’s findings of fact; a finding is clearly erroneous when, although evidence supports it, the reviewing court is left with a definite and firm conviction that a mistake has been made. In re BZ, 264 Mich. App. 286, 295, 690 N.W.2d 505 (2004). To establish jurisdiction at adjudication, the petitioner bears the burden to prove by a preponderance of the evidence that a statutory ground under MCL 712A.2(b) exists. In re Brock, 442 Mich. 101, 108–09, 499 N.W.2d 752 (1993). Rule: A court may assume jurisdiction if, and only if, the petitioner proves a qualifying statutory ground under either subsection (b)(1) or (b)(2) with respect to a juvenile under 18 found within the county. (biomarker: ||MCL 712A.2|| e-9334f9e9-ddaa-485e-9894-e22e47a8fec5) Under (b)(1), the petitioner must show that a parent or other legally responsible person, when able to do so, neglected or refused to provide proper or necessary support, education, medical, surgical, or other care necessary for the child’s health or morals, or that the child was subject to a substantial risk of harm to mental well-being, abandoned, or without proper custody/guardianship, with “neglect” defined by statute. (biomarker: ||MCL 712A.2|| e-5cea6761-bab2-4941-a6c8-adf6c5052ef4); (biomarker: ||MCL 712A.2|| e-6fbedc92-6651-46b2-a8b4-cdbc4ec11b2a); (biomarker: ||MCL 722.602|| e-64695679-3c0e-49b0-8e73-ab0833979053) The “without proper custody or guardianship” clause does not reach circumstances in which a parent places the child with a legally responsible caregiver who is able to and does provide proper care and maintenance. (biomarker: ||MCL 712A.2|| e-ad745b5a-1430-414f-a34c-d0c7c7eb37af) Under (b)(2), the petitioner must show that the child’s home or environment is an unfit place to live by reason of specified parental fault—including “neglect,” which carries the statutory meaning in MCL 722.602(1)(d). (biomarker: ||MCL 712A.2|| e-0488d0f0-04bd-4686-9be7-c25cf67256c4); (biomarker: ||MCL 722.602|| e-64695679-3c0e-49b0-8e73-ab0833979053) In applying these subsections, the court evaluates whether the statutory elements are satisfied as to the respondent parent, including whether any alleged “neglect” reflects negligent treatment within the statutory definition, and whether the child presently falls within the statute at the time jurisdiction is invoked. (biomarker: ||MCL 712A.2|| e-5cea6761-bab2-4941-a6c8-adf6c5052ef4); (biomarker: ||MCL 712A.2|| e-0488d0f0-04bd-4686-9be7-c25cf67256c4); (biomarker: ||MCL 722.602|| e-64695679-3c0e-49b0-8e73-ab0833979053) Because “neglect” and “unfitness” are statutorily circumscribed, evidence that a parent arranged appropriate alternate care or made safety‑driven placement decisions consistent with maintaining the child’s health and welfare may be inconsistent with the statutory “neglect” required under either subsection, whereas proof that a parent, when able, refused or failed to provide necessary care or maintained an unfit home by reason of neglect, cruelty, drunkenness, criminality, or depravity satisfies the statute. (biomarker: ||MCL 712A.2|| e-5cea6761-bab2-4941-a6c8-adf6c5052ef4); (biomarker: ||MCL 712A.2|| e-0488d0f0-04bd-4686-9be7-c25cf67256c4); (biomarker: ||MCL 722.602|| e-64695679-3c0e-49b0-8e73-ab0833979053) In a contested case such as this one, jurisdiction is therefore proper only if the record at adjudication establishes, by a preponderance, that the respondent mother’s conduct meets the statutory definition of “neglect” under MCL 722.602(1)(d) and falls within either (b)(1) or (b)(2), or that another listed parental fault under (b)(2) renders the home “an unfit place” for the child to live; otherwise, jurisdiction must be denied. In re Brock, 442 Mich. at 108–09; In re BZ, 264 Mich. App. at 295(biomarker: ||MCL 712A.2|| e-5cea6761-bab2-4941-a6c8-adf6c5052ef4); (biomarker: ||MCL 712A.2|| e-0488d0f0-04bd-4686-9be7-c25cf67256c4); (biomarker: ||MCL 722.602|| e-64695679-3c0e-49b0-8e73-ab0833979053) |~~"
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
    rules_to_doctrinal_overview_result_temp = await Runner.run(
      rules_to_doctrinal_overview,
      input=[
        *conversation_history
      ],
      run_config=RunConfig(trace_metadata={
        "__trace_source__": "agent-builder",
        "workflow_id": "wf_68e7b11283cc819089feb87b7b2614d10a841251773a70d5"
      })
    )

    conversation_history.extend([item.to_input_item() for item in rules_to_doctrinal_overview_result_temp.new_items])

    rules_to_doctrinal_overview_result = {
      "output_text": rules_to_doctrinal_overview_result_temp.final_output_as(str)
    }
    conform_to_legal_writing_result_temp = await Runner.run(
      conform_to_legal_writing,
      input=[
        *conversation_history
      ],
      run_config=RunConfig(trace_metadata={
        "__trace_source__": "agent-builder",
        "workflow_id": "wf_68e7b11283cc819089feb87b7b2614d10a841251773a70d5"
      })
    )

    conversation_history.extend([item.to_input_item() for item in conform_to_legal_writing_result_temp.new_items])

    conform_to_legal_writing_result = {
      "output_text": conform_to_legal_writing_result_temp.final_output_as(str)
    }
    guardrails_inputtext = conform_to_legal_writing_result["output_text"]
    guardrails_result = await run_guardrails(ctx, guardrails_inputtext, "text/plain", instantiate_guardrails(load_config_bundle(guardrails_config)), suppress_tripwire=True)
    guardrails_hastripwire = guardrails_has_tripwire(guardrails_result)
    guardrails_anonymizedtext = get_guardrail_checked_text(guardrails_result, guardrails_inputtext)
    guardrails_output = (guardrails_hastripwire and build_guardrail_fail_output(guardrails_result or [])) or (guardrails_anonymizedtext or guardrails_inputtext)
    if guardrails_hastripwire:
      raise Exception(f"Guardrails tripwire triggered: {guardrails_output}")
    else:
      return guardrails_output
