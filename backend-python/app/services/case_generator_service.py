from __future__ import annotations

import json
import re
import uuid
from typing import Any

from app.services.open_patients_rag import OpenPatientsRagService


_CASE_GENERATION_SYSTEM_PROMPT = """
You are a clinical education designer. Given a real-world de-identified patient description,
generate a structured patient case for medical student interview training.

You MUST output ONLY a single valid JSON object — no markdown fences, no preamble, no trailing text.

The JSON must have exactly these fields:
{
  "id": "<a short unique slug, e.g. gen-abc123>",
  "name": "<realistic patient name matching gender/culture>",
  "age": <integer>,
  "gender": "<Male|Female|Other>",
  "initialComplaint": "<1-2 sentence opening the patient would say when asked why they came in — colloquial, first-person>",
  "hiddenDetails": {
    "duration": "<how long the complaint has been present — patient's own words>",
    "triggers": "<what makes symptoms worse or what brought them on>",
    "pastHistory": "<relevant past medical conditions>",
    "associatedSymptoms": "<other symptoms the patient experiences>",
    "lifestyle": "<smoking, alcohol, occupation, exercise — brief>",
    "familyHistory": "<relevant family history, or null>",
    "drugHistory": "<current medications or null>",
    "reviewOfSystems": "<any other system findings or null>"
  },
  "physicalExam": [
    {"system": "<system name>", "finding": "<examination finding>"}
  ],
  "correctDiagnosis": "<the most likely diagnosis>",
  "difficulty": "<easy|medium|hard>",
  "differentials": ["<differential 1>", "<differential 2>", "<differential 3>"],
  "redFlags": ["<red flag symptom 1>", "<red flag symptom 2>"],
  "mustAskItems": [
    {
      "dimension": "<HPC|PMH|DH|FH|SH|ROS|ICE|COMM>",
      "subItem": "<specific topic to cover>",
      "critical": <true|false>,
      "hint": "<coaching hint for students>"
    }
  ],
  "personality": "<2-3 sentence description of patient personality and communication style>",
  "speechPatterns": ["<e.g. [*sighs*]>", "<verbal filler or mannerism>"]
}

Rules:
- mustAskItems must cover ALL 8 dimensions (HPC, PMH, DH, FH, SH, ROS, ICE, COMM), with at least 1 item each.
- HPC must have at least 3 items, including onset/duration and a key associated symptom.
- Mark 4-6 items as critical:true — these are clinically essential.
- difficulty: easy = classic presentation, medium = subtle/mixed, hard = atypical/comorbid.
- physicalExam: 2-4 findings across different systems, medically consistent with the diagnosis.
- differentials: exactly 3, clinically plausible alternatives to the correct diagnosis.
- redFlags: 2-4 symptoms that would indicate serious deterioration.
- initialComplaint must sound like a real patient, not a textbook description.
- Infer a realistic name from the patient's apparent demographics in the description.
- Do NOT copy sentences verbatim from the source description.
- Output ONLY the JSON. No explanation, no markdown.
""".strip()


class CaseGeneratorService:
    """Generates a full PatientCase structure from an Open-Patients description using an LLM."""

    def __init__(self) -> None:
        self.rag_service = OpenPatientsRagService()

    def generate_random_case(self, config: dict[str, Any], difficulty: str = 'medium') -> dict[str, Any] | None:
        """Sample a random Open-Patients case and use LLM to generate a full PatientCase."""
        rag_case = self.rag_service.sample_case()
        if not rag_case:
            return None

        return self._generate_case_from_description(rag_case.description, rag_case.case_id, difficulty, config)

    def _generate_case_from_description(
        self,
        description: str,
        source_id: str,
        difficulty: str,
        config: dict[str, Any],
    ) -> dict[str, Any] | None:
        from app.services.ai_service import AIService

        ai_service = AIService()
        compact = re.sub(r'\s+', ' ', description).strip()

        user_message = (
            f"Difficulty level requested: {difficulty}\n\n"
            f"Patient description:\n{compact[:6000]}"
        )

        try:
            raw = ai_service.generate_text(
                provider=config['textProvider'],
                system_prompt=_CASE_GENERATION_SYSTEM_PROMPT,
                messages=[{'role': 'user', 'content': user_message}],
                temperature=0.6,
                model=config.get('textModel'),
                api_key=config.get('textApiKey'),
                base_url=config.get('textBaseUrl'),
            )
        except Exception:
            return None

        case_data = self._parse_case_json(raw)
        if not case_data:
            return None

        # Ensure valid id and difficulty
        case_data['id'] = f"gen-{source_id[:8]}-{uuid.uuid4().hex[:6]}"
        if case_data.get('difficulty') not in ('easy', 'medium', 'hard'):
            case_data['difficulty'] = difficulty

        return case_data

    def _parse_case_json(self, raw: str) -> dict[str, Any] | None:
        # Strip markdown fences if present
        text = raw.strip()
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        text = text.strip()

        # Find the first top-level JSON object
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if not match:
            return None

        try:
            data = json.loads(match.group())
        except json.JSONDecodeError:
            return None

        # Validate required fields
        required = {'name', 'age', 'gender', 'initialComplaint', 'hiddenDetails',
                    'correctDiagnosis', 'difficulty', 'mustAskItems'}
        if not required.issubset(data.keys()):
            return None

        # Ensure list fields exist
        data.setdefault('physicalExam', [])
        data.setdefault('differentials', [])
        data.setdefault('redFlags', [])
        data.setdefault('speechPatterns', [])

        # Ensure hiddenDetails has all required sub-fields
        hd = data.get('hiddenDetails', {})
        for field in ('duration', 'triggers', 'pastHistory', 'associatedSymptoms', 'lifestyle'):
            hd.setdefault(field, 'Not reported.')
        data['hiddenDetails'] = hd

        return data
