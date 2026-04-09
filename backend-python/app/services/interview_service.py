from __future__ import annotations

import re
import time
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.services.open_patients_rag import OpenPatientsRagService

_SUMMARY_DIR = Path('/tmp/clinical_simulator/summaries')

ALL_DIMENSIONS = ['HPC', 'PMH', 'DH', 'FH', 'SH', 'ROS', 'ICE', 'COMM']

SUMMARY_INTERVAL = 5   # regenerate conversation summary every N turns
RECENT_WINDOW = 6      # number of recent turns passed raw to the LLM


class InterviewService:
    def __init__(self) -> None:
        self._turn_chain = None
        self.rag_service = OpenPatientsRagService()
        self.ai_service = None

    @property
    def turn_chain(self):
        if self._turn_chain is None:
            from app.llm.chains.interview_chain import InterviewTurnChain

            self._turn_chain = InterviewTurnChain()
        return self._turn_chain

    def create_initial_state(self, case_data: dict[str, Any]) -> dict[str, Any]:
        dimension_coverages = []
        for dim in ALL_DIMENSIONS:
            total_items = len([item for item in case_data['mustAskItems'] if item['dimension'] == dim])
            dimension_coverages.append({
                'dimension': dim,
                'coveredItems': [],
                'totalItems': total_items,
                'percentage': 0,
            })
        return {
            'phase': 'OPENING',
            'turnCount': 0,
            'turnsWithoutProgress': 0,
            'dimensionCoverages': dimension_coverages,
            'overallCoverage': 0,
            'events': [],
            'extractions': [],
            'ragCaseId': None,
            'ragCaseSummary': None,
            'sessionId': str(uuid.uuid4()),
        }

    def add_event(self, state: dict[str, Any], event_type: str, data: dict[str, Any] | None = None) -> None:
        state['events'].append({
            'type': event_type,
            'turn': state['turnCount'],
            'timestamp': int(time.time() * 1000),
            'data': data or {},
        })

    def _normalize_summary(self, text: str, max_chars: int = 900) -> str:
        return re.sub(r'\s+', ' ', text).strip()[:max_chars]

    def _get_ai_service(self):
        if self.ai_service is not None:
            return self.ai_service
        try:
            from app.services.ai_service import AIService
        except Exception:
            return None
        self.ai_service = AIService()
        return self.ai_service

    def _summarize_rag_description(self, description: str, config: dict[str, Any]) -> str | None:
        compact_description = re.sub(r'\s+', ' ', description).strip()
        if not compact_description:
            return None
        ai_service = self._get_ai_service()
        if ai_service is None:
            return None

        system_prompt = (
            'You are a clinical communication editor. '
            'Summarize a de-identified patient description into a concise simulation brief for role-play. '
            'Output plain English only, no markdown, 80-140 words, and include: demographics, chief complaint timeline, '
            'key associated symptoms, relevant background, and speaking style. '
            'Preserve uncertainty, do not invent tests, and do not add management advice.'
        )

        try:
            summary = ai_service.generate_text(
                provider=config['textProvider'],
                system_prompt=system_prompt,
                messages=[
                    {
                        'role': 'user',
                        'content': f'Description:\n{compact_description[:7000]}',
                    }
                ],
                temperature=0.2,
                model=config.get('textModel'),
                api_key=config.get('textApiKey'),
                base_url=config.get('textBaseUrl'),
            )
            normalized = self._normalize_summary(summary)
            return normalized or None
        except Exception:
            return None

    # ── File-based summary storage ──────────────────────────────────────────

    @staticmethod
    def _summary_path(session_id: str) -> Path:
        return _SUMMARY_DIR / f'{session_id}.txt'

    @staticmethod
    def _read_summary(session_id: str) -> str | None:
        try:
            path = InterviewService._summary_path(session_id)
            return path.read_text(encoding='utf-8').strip() or None
        except FileNotFoundError:
            return None

    @staticmethod
    def _write_summary(session_id: str, summary: str) -> None:
        _SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
        InterviewService._summary_path(session_id).write_text(summary, encoding='utf-8')

    @staticmethod
    def delete_session_summary(session_id: str) -> None:
        """Remove the summary file for a session. Safe to call even if the file doesn't exist."""
        try:
            InterviewService._summary_path(session_id).unlink(missing_ok=True)
        except Exception:
            pass

    def _refresh_summary(
        self,
        session_id: str,
        history: list[dict[str, Any]],
        config: dict[str, Any],
    ) -> None:
        """Generate an updated summary from full history and persist to file."""
        if not history:
            return

        ai_service = self._get_ai_service()
        if ai_service is None:
            return

        prev_summary = self._read_summary(session_id)
        turns_text = '\n'.join(
            f"{'Student' if m['role'] == 'student' else 'Patient'}: {m['text']}"
            for m in history
        )
        prev_block = f'Previous summary:\n{prev_summary}\n\n' if prev_summary else ''
        system_prompt = (
            'You are a clinical conversation summariser. '
            'Given a medical student–patient interview transcript, produce a concise running summary '
            'in the style of a clinical note. Cover: what the student has asked, what the patient '
            'has revealed (symptoms, timeline, PMH, DH, FH, SH, ROS), and any notable gaps. '
            'Plain English only, no markdown, maximum 200 words. '
            'If a previous summary is provided, update it rather than replacing it.'
        )
        try:
            result = ai_service.generate_text(
                provider=config['textProvider'],
                system_prompt=system_prompt,
                messages=[{
                    'role': 'user',
                    'content': f'{prev_block}New turns:\n{turns_text}',
                }],
                temperature=0.1,
                model=config.get('textModel'),
                api_key=config.get('textApiKey'),
                base_url=config.get('textBaseUrl'),
            )
            normalized = self._normalize_summary(result, max_chars=1200)
            if normalized:
                self._write_summary(session_id, normalized)
        except Exception:
            pass  # keep existing file content on failure

    def _ensure_rag_context(self, state: dict[str, Any], config: dict[str, Any]) -> None:
        if state.get('ragCaseSummary'):
            return

        rag_case = self.rag_service.sample_case()
        if not rag_case:
            return

        model_summary = self._summarize_rag_description(rag_case.description, config)
        summary = model_summary or rag_case.summary
        if not summary:
            return

        state['ragCaseId'] = rag_case.case_id
        state['ragCaseSummary'] = summary
        self.add_event(
            state,
            'rag_case_selected',
            {
                'caseId': rag_case.case_id,
                'summarySource': 'llm' if model_summary else 'heuristic_fallback',
            },
        )

    @staticmethod
    def _topic_tokens(text: str) -> set[str]:
        """Return meaningful word tokens from a topic string, ignoring short stop words."""
        stop = {'of', 'the', 'a', 'an', 'and', 'or', 'in', 'to', 'for', 'with', 'on', 'at', 'is', 'are', 'was'}
        return {w for w in re.sub(r'[^a-z0-9 ]', '', text.lower()).split() if w not in stop and len(w) > 1}

    def _topic_matches(self, extracted: str, must_ask: str, confidence: float) -> bool:
        """Return True if extracted topic is a meaningful match for a must-ask item."""
        if confidence >= 0.7:
            return True
        a = self._topic_tokens(extracted)
        b = self._topic_tokens(must_ask)
        if not a or not b:
            return False
        # Accept if at least one meaningful token is shared and the smaller set overlaps >= 50%
        overlap = a & b
        if not overlap:
            return False
        smaller = min(len(a), len(b))
        return len(overlap) / smaller >= 0.5

    def update_coverage(self, state: dict[str, Any], case_data: dict[str, Any], extraction: dict[str, Any]) -> bool:
        any_new = False
        for item in extraction.get('topicsCovered', []):
            dim_coverage = next((d for d in state['dimensionCoverages'] if d['dimension'] == item['dimension']), None)
            if not dim_coverage:
                continue
            already_covered = any(existing.lower() == item['subItem'].lower() for existing in dim_coverage['coveredItems'])
            if already_covered:
                continue
            confidence = item.get('confidence', 0)
            matches_must_ask = any(
                must['dimension'] == item['dimension'] and
                self._topic_matches(item['subItem'], must['subItem'], confidence)
                for must in case_data['mustAskItems']
            )
            if matches_must_ask or confidence >= 0.6:
                dim_coverage['coveredItems'].append(item['subItem'])
                any_new = True

        for dim in state['dimensionCoverages']:
            dim['percentage'] = min(100, round((len(dim['coveredItems']) / dim['totalItems']) * 100)) if dim['totalItems'] > 0 else 0

        total_must = len(case_data['mustAskItems'])
        total_covered = sum(len(d['coveredItems']) for d in state['dimensionCoverages'])
        state['overallCoverage'] = min(100, round((total_covered / total_must) * 100)) if total_must > 0 else 0

        if any_new:
            self.add_event(state, 'coverage_update', {'overallCoverage': state['overallCoverage']})
        return any_new

    def check_phase_transition(self, state: dict[str, Any]) -> None:
        prev = state['phase']
        if state['phase'] == 'OPENING':
            if state['turnCount'] >= 1 and state['overallCoverage'] > 0:
                state['phase'] = 'HISTORY_TAKING'
        elif state['phase'] == 'HISTORY_TAKING':
            well_covered = len([d for d in state['dimensionCoverages'] if d['totalItems'] > 0 and d['percentage'] >= 60])
            if well_covered >= 3:
                state['phase'] = 'GUIDED_INQUIRY'
        elif state['phase'] == 'GUIDED_INQUIRY':
            if state['overallCoverage'] >= 60 or state['turnCount'] >= 15:
                state['phase'] = 'DIAGNOSIS_READY'

        if state['phase'] != prev:
            self.add_event(state, 'phase_change', {'from': prev, 'to': state['phase']})

    def get_critical_gaps(self, state: dict[str, Any], case_data: dict[str, Any]) -> list[dict[str, Any]]:
        covered = set()
        for dim in state['dimensionCoverages']:
            for item in dim['coveredItems']:
                covered.add(item.lower())
        gaps = []
        for item in case_data['mustAskItems']:
            if not item.get('critical'):
                continue
            found = any(
                c.split(' ')[0] in item['subItem'].lower() or item['subItem'].lower().split(' ')[0] in c
                for c in covered
            )
            if not found:
                gaps.append(item)
        return gaps

    def get_next_hint(self, state: dict[str, Any], case_data: dict[str, Any]) -> str | None:
        gaps = self.get_critical_gaps(state, case_data)
        if not gaps:
            return None
        with_hint = next((g for g in gaps if g.get('hint')), None)
        if with_hint:
            return with_hint['hint']
        gap = gaps[0]
        return f"Consider asking about: {gap['subItem']} ({gap['dimension']})"

    def evaluate_decision(self, state: dict[str, Any], case_data: dict[str, Any]) -> dict[str, Any]:
        if state['turnCount'] >= 10:
            critical_gaps = self.get_critical_gaps(state, case_data)
            if critical_gaps:
                gap = critical_gaps[0]
                hint = gap.get('hint')
                message = f'Coach tip: You haven\'t explored an important area yet. Consider asking: "{hint}"' if hint else f"Coach tip: Don't forget to ask about {gap['subItem']}."
                return {'type': 'RED_FLAG', 'message': message, 'data': {'missingItem': gap['subItem']}}

        if state['turnsWithoutProgress'] >= 3:
            hint = self.get_next_hint(state, case_data)
            if hint:
                return {'type': 'HINT_NEEDED', 'message': f'Coach tip: {hint}'}

        if state['extractions']:
            last = state['extractions'][-1]
            if last.get('clinicalRelevance') == 'off_track' and state['turnsWithoutProgress'] >= 2:
                return {
                    'type': 'RISK_BRANCH',
                    'message': 'Coach tip: Your recent questions may not be leading toward the core diagnosis. Consider refocusing on the presenting complaint.',
                }

        if state['phase'] == 'GUIDED_INQUIRY' and state['overallCoverage'] >= 60:
            return {
                'type': 'PHASE_ADVANCE',
                'message': 'You have gathered sufficient information. You may now submit your diagnosis when ready.',
            }

        return {'type': 'CONTINUE'}

    def process_turn(self, case_data: dict[str, Any], history: list[dict[str, Any]], student_input: str, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        next_state = deepcopy(state) if state else self.create_initial_state(case_data)
        self._ensure_rag_context(next_state, config)

        session_id = next_state.get('sessionId') or ''

        # ── Memory: read summary from file; pass only recent window to LLM ──
        conversation_summary = self._read_summary(session_id) if session_id else None
        recent_history = history[-RECENT_WINDOW:] if len(history) > RECENT_WINDOW else history

        parsed = self.turn_chain.invoke(
            case_data=case_data,
            history=recent_history,
            student_input=student_input,
            config=config,
            rag_case_summary=next_state.get('ragCaseSummary'),
            conversation_summary=conversation_summary,
        )
        extraction = parsed.extraction.model_dump(by_alias=True) if parsed.extraction else None

        next_state['turnCount'] += 1
        if extraction:
            next_state['extractions'].append(extraction)
            had_progress = self.update_coverage(next_state, case_data, extraction)
            next_state['turnsWithoutProgress'] = 0 if had_progress else next_state['turnsWithoutProgress'] + 1
        else:
            next_state['turnsWithoutProgress'] += 1
        self.check_phase_transition(next_state)
        decision = self.evaluate_decision(next_state, case_data)

        # ── Memory: persist refreshed summary to file every SUMMARY_INTERVAL turns ──
        if session_id and next_state['turnCount'] % SUMMARY_INTERVAL == 0 and history:
            self._refresh_summary(session_id, history, config)

        return {
            'patientMessage': {
                'role': 'patient',
                'text': parsed.patient_response or "I'm sorry, I'm feeling a bit confused right now...",
            },
            'extraction': extraction,
            'sessionState': next_state,
            'decision': decision,
        }
