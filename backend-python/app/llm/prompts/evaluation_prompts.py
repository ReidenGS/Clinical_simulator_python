from __future__ import annotations

import json


EVALUATION_PROMPT_VERSION = 'v3-rag'

# Dimensions where the RAG real-world reference adds meaningful evaluation signal.
# - clinical_reasoning: assess whether the student probed the nuanced presentation
#   patterns that real patients with this condition typically exhibit.
# - communication: assess whether the student adapted to the colloquial, realistic
#   response style that the RAG reference anchored the patient simulation to.
# Excluded intentionally:
# - diagnostic_accuracy: must stay anchored to correctDiagnosis, not RAG narrative.
# - safety: must stay anchored to the structured red-flag list, not RAG narrative.
# - info_gathering / efficiency: deterministic, not affected by this prompt.
_RAG_AWARE_DIMENSIONS = {'clinical_reasoning', 'communication'}


def build_dimension_evaluation_prompt(
    dim: dict,
    session_state: dict,
    diagnosis: str,
    case_data: dict,
    format_instructions: str,
):
    from langchain_core.prompts import ChatPromptTemplate

    # Extract RAG summary from session state — present only when the RAG pipeline ran.
    rag_case_summary: str | None = session_state.get('ragCaseSummary') or None

    # Build the optional RAG context block, only for applicable dimensions.
    rag_block = ''
    if rag_case_summary and dim.get('id') in _RAG_AWARE_DIMENSIONS:
        if dim['id'] == 'clinical_reasoning':
            rag_block = f"""
REAL-WORLD PRESENTATION REFERENCE (RAG):
During this session the patient simulation was anchored to the following real-world
case narrative (de-identified). Use it to assess whether the student's questions
probed the nuanced presentation patterns — timeline, associated symptoms, and
contextual details — that real patients with this condition actually describe.
Do NOT use it to override the correct diagnosis.
  {rag_case_summary}
""".strip()
        elif dim['id'] == 'communication':
            rag_block = f"""
REAL-WORLD EXPRESSION REFERENCE (RAG):
The patient's responses in this session were stylistically anchored to the following
real-world narrative (de-identified). Use it when assessing whether the student
responded appropriately to colloquial, non-textbook language and whether they showed
empathy toward the realistic emotional tone the patient expressed.
Do NOT use it to override the correct diagnosis or coverage data.
  {rag_case_summary}
""".strip()

    user_prompt = f"""
You are evaluating a medical student's clinical interview on the dimension: {dim['name']}.
Description: {dim['description']}

CASE: {case_data['name']}, {case_data['age']}y {case_data['gender']}
CORRECT DIAGNOSIS: {case_data['correctDiagnosis']}
STUDENT DIAGNOSIS: {diagnosis}

SESSION DATA:
- Total turns: {session_state['turnCount']}
- Phase reached: {session_state['phase']}
- Overall coverage: {session_state['overallCoverage']}%
- Dimension coverages: {json.dumps([{'dim': d['dimension'], 'pct': d['percentage'], 'items': d['coveredItems']} for d in session_state['dimensionCoverages']])}
- Student approach patterns: {json.dumps([e.get('studentApproach') for e in session_state['extractions'] if e.get('studentApproach')])}
- Clinical relevance: {json.dumps([e.get('clinicalRelevance') for e in session_state['extractions'] if e.get('clinicalRelevance')])}
{(chr(10) + rag_block) if rag_block else ''}
Score strictly based on the evidence above.
Prompt version: {EVALUATION_PROMPT_VERSION}
{format_instructions}
""".strip()

    return ChatPromptTemplate.from_messages([
        ('system', 'You are a strict but fair evaluator for medical interview training.'),
        ('human', user_prompt),
    ])
