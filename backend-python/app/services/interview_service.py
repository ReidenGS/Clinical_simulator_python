from __future__ import annotations

import time
from copy import deepcopy
from typing import Any

ALL_DIMENSIONS = ['HPC', 'PMH', 'DH', 'FH', 'SH', 'ROS', 'ICE', 'COMM']


class InterviewService:
    def __init__(self) -> None:
        self._turn_chain = None

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
        }

    def add_event(self, state: dict[str, Any], event_type: str, data: dict[str, Any] | None = None) -> None:
        state['events'].append({
            'type': event_type,
            'turn': state['turnCount'],
            'timestamp': int(time.time() * 1000),
            'data': data or {},
        })

    def update_coverage(self, state: dict[str, Any], case_data: dict[str, Any], extraction: dict[str, Any]) -> bool:
        any_new = False
        for item in extraction.get('topicsCovered', []):
            dim_coverage = next((d for d in state['dimensionCoverages'] if d['dimension'] == item['dimension']), None)
            if not dim_coverage:
                continue
            already_covered = any(existing.lower() == item['subItem'].lower() for existing in dim_coverage['coveredItems'])
            if already_covered:
                continue
            matches_must_ask = any(
                must['dimension'] == item['dimension'] and (
                    item['subItem'].lower().split(' ')[0] in must['subItem'].lower() or
                    must['subItem'].lower().split(' ')[0] in item['subItem'].lower() or
                    item.get('confidence', 0) >= 0.7
                )
                for must in case_data['mustAskItems']
            )
            if matches_must_ask or item.get('confidence', 0) >= 0.6:
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
        parsed = self.turn_chain.invoke(
            case_data=case_data,
            history=history,
            student_input=student_input,
            config=config,
        )
        extraction = parsed.extraction.model_dump(by_alias=True) if parsed.extraction else None

        next_state = deepcopy(state) if state else self.create_initial_state(case_data)
        next_state['turnCount'] += 1
        if extraction:
            next_state['extractions'].append(extraction)
            had_progress = self.update_coverage(next_state, case_data, extraction)
            next_state['turnsWithoutProgress'] = 0 if had_progress else next_state['turnsWithoutProgress'] + 1
        else:
            next_state['turnsWithoutProgress'] += 1
        self.check_phase_transition(next_state)
        decision = self.evaluate_decision(next_state, case_data)

        return {
            'patientMessage': {
                'role': 'patient',
                'text': parsed.patient_response or "I'm sorry, I'm feeling a bit confused right now...",
            },
            'extraction': extraction,
            'sessionState': next_state,
            'decision': decision,
        }
