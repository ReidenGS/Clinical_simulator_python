from __future__ import annotations

import json


EVALUATION_PROMPT_VERSION = 'v2'


def build_dimension_evaluation_prompt(
    dim: dict,
    session_state: dict,
    diagnosis: str,
    case_data: dict,
    format_instructions: str,
):
    from langchain_core.prompts import ChatPromptTemplate

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

Score strictly based on the evidence above.
Prompt version: {EVALUATION_PROMPT_VERSION}
{format_instructions}
""".strip()

    return ChatPromptTemplate.from_messages([
        ('system', 'You are a strict but fair evaluator for medical interview training.'),
        ('human', user_prompt),
    ])
