from __future__ import annotations


INTERVIEW_PROMPT_VERSION = 'v3-rag'


def build_extraction_instruction(case_data: dict) -> str:
    dimensions = "\n".join(
        f"- {item['dimension']}: {item['subItem']}" for item in case_data['mustAskItems']
    )
    return f"""
After composing the patient reply, also analyze what the student asked this turn.
Return JSON matching the required schema.

Trackable items for this case:
{dimensions}

Rules:
- patientResponse must stay fully in character and colloquial.
- Only include topicsCovered items that were actually asked in this turn.
- If the student asked nothing clinically relevant, topicsCovered can be empty.
- confidence should reflect how directly the student asked about the item.
""".strip()


def build_patient_turn_prompt(case_data: dict, format_instructions: str, rag_case_summary: str | None = None, conversation_summary: str | None = None):
    from langchain_core.prompts import ChatPromptTemplate

    family_history = case_data['hiddenDetails'].get('familyHistory')
    drug_history = case_data['hiddenDetails'].get('drugHistory')
    review_of_systems = case_data['hiddenDetails'].get('reviewOfSystems')
    personality = case_data.get('personality')
    speech_patterns = case_data.get('speechPatterns') or []

    rag_context = ''
    if rag_case_summary:
        rag_context = f"""
REAL-WORLD REFERENCE (RAG, de-identified):
- Use this as a realism anchor for symptom expression and chronology:
  {rag_case_summary}
- Never copy sentences verbatim.
- Keep priority order: structured CASE FACTS > diagnosis consistency > RAG reference.
""".strip()

    memory_context = ''
    if conversation_summary:
        memory_context = f"""
CONVERSATION MEMORY (auto-summary of earlier turns not in the message history below):
{conversation_summary}
- Use this to stay consistent. Do NOT re-ask what the patient has already revealed.
- The recent message history below takes priority over this summary if they conflict.
""".strip()

    # Escape braces in format_instructions so LangChain doesn't treat JSON schema
    # keys like {"$defs"} as template variables.
    safe_format_instructions = format_instructions.replace('{', '{{').replace('}', '}}')

    system_prompt = f"""
ROLE: You are simulating a patient named {case_data['name']} ({case_data['age']}y, {case_data['gender']}) for a medical student's training.
DIAGNOSIS: The underlying condition you have is {case_data['correctDiagnosis']}. You must stay strictly consistent with the typical symptoms and progression of this condition.

CASE FACTS:
- Initial Complaint: {case_data['initialComplaint']}
- Duration: {case_data['hiddenDetails']['duration']}
- Triggers: {case_data['hiddenDetails']['triggers']}
- Past History: {case_data['hiddenDetails']['pastHistory']}
- Associated Symptoms: {case_data['hiddenDetails']['associatedSymptoms']}
- Lifestyle: {case_data['hiddenDetails']['lifestyle']}
{f'- Family History: {family_history}' if family_history else ''}
{f'- Drug History: {drug_history}' if drug_history else ''}
{f'- Review of Systems: {review_of_systems}' if review_of_systems else ''}
{f'PERSONALITY: {personality}' if personality else ''}
{f"SPEECH PATTERNS (use these naturally): {', '.join(speech_patterns)}" if speech_patterns else ''}
{rag_context}
{memory_context}

STRICT GUIDELINES:
1. DO NOT volunteer hidden details unless explicitly asked.
2. If asked about something not in the facts, provide an answer medically consistent with {case_data['correctDiagnosis']}.
3. Use colloquial, non-medical language.
4. Maintain a consistent personality.
5. Include realistic symptom sounds in brackets if relevant, such as [*coughs*], [*wheezes*], [*heavy breathing*], [*gasps for air*].
6. NEVER break character. Do not say you are an AI.
7. Prompt version: {INTERVIEW_PROMPT_VERSION}

{build_extraction_instruction(case_data)}

{safe_format_instructions}
""".strip()

    return ChatPromptTemplate.from_messages([
        ('system', system_prompt),
        ('placeholder', '{history_messages}'),
        ('human', '{student_input}'),
    ])
