from __future__ import annotations

import time
from typing import Any

from app.services.cpr_guideline_rag import CprGuidelineRagService

PHASE_INSTRUCTIONS = {
    'BRIEFING': 'Review the scenario and press Confirm when ready to begin.',
    'SCENE_SAFETY': 'Look around for hazards. Is the scene safe to approach? Press Confirm.',
    'CHECK_RESPONSE': 'Tap the victim on the shoulder and shout "Are you okay?" Press Confirm.',
    'CALL_FOR_HELP': 'Call 911 (or direct a bystander to call) and request an AED. Press Confirm.',
    'CHECK_BREATHING': 'Look, listen, and feel for breathing (max 10 seconds). Press Confirm.',
    'VENTILATION': 'Tilt the head, lift the chin, and deliver 2 rescue breaths. Press Confirm.',
    'AED_PROMPT': 'An AED has arrived. Follow the AED voice prompts. Press Confirm.',
    'CYCLE_BREAK': 'Switch rescuers! You have been compressing for 2 minutes. Rest and press Confirm to resume.',
}

BLS_CHECKLIST_LABELS = [
    'Confirm scene safety',
    'Check responsiveness (tap and shout)',
    'Call 911 / activate EMS',
    'Check breathing (look-listen-feel)',
    'Begin chest compressions',
    'Deliver rescue breaths (30:2)',
    'Maintain target rhythm (100-120 CPM)',
    'Keep hands centered with straight arms',
]

HANDS_ONLY_CHECKLIST_LABELS = [
    'Confirm presence and body positioning',
    'Start continuous chest compressions',
    'Maintain target rhythm',
    'Keep hands centered with straight arms',
]

BLS_PHASE_ORDER = [
    'BRIEFING',
    'SCENE_SAFETY',
    'CHECK_RESPONSE',
    'CALL_FOR_HELP',
    'CHECK_BREATHING',
    'COMPRESSIONS',
    'VENTILATION',
    'AED_PROMPT',
    'CYCLE_BREAK',
    'ASSESSMENT',
    'COMPLETED',
]

CYCLE_DURATION_SECONDS = 120
COMPRESSIONS_PER_CYCLE_30_2 = 30


def clamp(value: float, min_value: float = 0, max_value: float = 100) -> float:
    return min(max_value, max(min_value, value))


def phase_at_or_past(current: str | None, target: str) -> bool:
    if not current:
        return False
    return BLS_PHASE_ORDER.index(current) >= BLS_PHASE_ORDER.index(target)


class CprService:
    def __init__(self) -> None:
        self.guideline_rag = CprGuidelineRagService()

    def _build_result(
        self,
        session_state: dict[str, Any],
        runtime_state: dict[str, Any] | None,
        decision: dict[str, Any],
        transition_events: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            'sessionState': session_state,
            'runtimeState': runtime_state,
            'decision': decision,
            'meta': {
                'usedFallback': False,
                'transitionEvents': transition_events or [],
            },
        }

    def prepare_guidelines(self, config: dict[str, Any] | None = None) -> dict[str, Any]:
        context = self.guideline_rag.get_guideline_context(config=config)
        return {
            'sourceUrl': context.source_url,
            'sourceTitle': context.source_title,
            'summary': context.summary,
            'standards': context.standards,
            'fetchedAt': context.fetched_at,
        }

    def _build_checklist(self, observations: list[dict[str, Any]], current_phase: str, scenario: dict[str, Any]) -> list[dict[str, Any]]:
        training_mode = scenario.get('trainingMode') or 'HANDS_ONLY'
        required = scenario.get('requiredFirstSteps') or []
        has_visible_hands = any(item.get('handsVisible') for item in observations)
        has_compression = any((item.get('compressionRate') or 0) > 0 for item in observations)
        within_rhythm = any(100 <= (item.get('compressionRate') or 0) <= 120 for item in observations)
        stable_form = any(item.get('handsVisible') and item.get('armsStraight') and item.get('handsCentered') for item in observations)

        def item(item_id: str, label: str, completed: bool, detail: str) -> dict[str, Any]:
            return {
                'id': item_id,
                'label': label,
                'completed': completed,
                'detail': detail,
            }

        if training_mode == 'CONVENTIONAL_30_2':
            reached_ventilation = phase_at_or_past(current_phase, 'VENTILATION') or (current_phase == 'COMPRESSIONS' and has_compression)
            return [
                item('scene_safety', BLS_CHECKLIST_LABELS[0], phase_at_or_past(current_phase, 'CHECK_RESPONSE'),
                     'Scene confirmed safe.' if phase_at_or_past(current_phase, 'CHECK_RESPONSE') else 'Confirm scene is safe before approaching.'),
                item('check_response', BLS_CHECKLIST_LABELS[1], phase_at_or_past(current_phase, 'CALL_FOR_HELP'),
                     'Responsiveness checked.' if phase_at_or_past(current_phase, 'CALL_FOR_HELP') else 'Tap the victim and shout to check for response.'),
                item('call_help', BLS_CHECKLIST_LABELS[2], phase_at_or_past(current_phase, 'CHECK_BREATHING'),
                     'EMS activated.' if phase_at_or_past(current_phase, 'CHECK_BREATHING') else 'Call 911 or direct someone to call.'),
                item('check_breathing', BLS_CHECKLIST_LABELS[3], phase_at_or_past(current_phase, 'COMPRESSIONS'),
                     'Breathing assessed.' if phase_at_or_past(current_phase, 'COMPRESSIONS') else 'Look, listen, and feel for breathing (max 10 seconds).'),
                item('compressions', BLS_CHECKLIST_LABELS[4], has_compression,
                     'Compression motion is being tracked.' if has_compression else 'Begin chest-compression movement.'),
                item('ventilation', BLS_CHECKLIST_LABELS[5], reached_ventilation,
                     'Rescue breaths delivered.' if reached_ventilation else 'After 30 compressions, deliver 2 rescue breaths.'),
                item('rhythm', BLS_CHECKLIST_LABELS[6], within_rhythm,
                     'Target cadence has been reached at least once.' if within_rhythm else 'Aim for 100-120 compressions per minute.'),
                item('form', BLS_CHECKLIST_LABELS[7], stable_form,
                     'Hands are centered and elbows stay straight.' if stable_form else 'Keep shoulders over hands and lock elbows.'),
            ]

        labels = required if len(required) >= 4 else HANDS_ONLY_CHECKLIST_LABELS
        return [
            item('position', labels[0], has_visible_hands,
                 'Upper body and hand landmarks are detected.' if has_visible_hands else 'Adjust camera and stance until hands are visible.'),
            item('compressions', labels[1], has_compression,
                 'Compression motion is being tracked.' if has_compression else 'Begin chest-compression movement to enter the active workflow.'),
            item('rhythm', labels[2], within_rhythm,
                 'Target cadence has been reached at least once.' if within_rhythm else 'Aim for 100-120 compressions per minute.'),
            item('form', labels[3], stable_form,
                 'Hands are centered and elbows stay straight.' if stable_form else 'Keep shoulders over hands and lock elbows.'),
        ]

    def _compute_rate_consistency(self, intervals: list[float]) -> int:
        if len(intervals) < 2:
            return 100
        mean = sum(intervals) / len(intervals)
        if mean == 0:
            return 100
        variance = sum((v - mean) ** 2 for v in intervals) / len(intervals)
        std_dev = variance ** 0.5
        cv = std_dev / mean
        return round(max(0, min(100, (1 - cv) * 100)))

    def ingest(self, observation: dict[str, Any], scenario: dict[str, Any], state: dict[str, Any] | None = None) -> dict[str, Any]:
        now_ms = int(time.time() * 1000)
        training_mode = scenario.get('trainingMode') or 'HANDS_ONLY'

        session_state_in = (state or {}).get('sessionState') or {}
        runtime_state_in = (state or {}).get('runtimeState') or {}

        observations = list(session_state_in.get('observations') or [])
        observations.append(observation)
        observations = [item for item in observations if observation['timestamp'] - item['timestamp'] <= 60000]

        rates = [item.get('compressionRate', 0) for item in observations if (item.get('compressionRate') or 0) > 0]
        visible_count = sum(1 for item in observations if item.get('handsVisible'))
        straight_count = sum(1 for item in observations if item.get('handsVisible') and item.get('armsStraight'))
        centered_count = sum(1 for item in observations if item.get('handsVisible') and item.get('handsCentered'))
        total = len(observations) or 1
        visible_ratio = visible_count / total
        straight_arm_ratio = 0 if visible_count == 0 else straight_count / visible_count
        centered_ratio = 0 if visible_count == 0 else centered_count / visible_count
        current_rate = rates[-1] if rates else 0
        average_rate = round(sum(rates) / len(rates)) if rates else 0
        max_rate = max(rates) if rates else 0

        previous_phase = session_state_in.get('currentPhase') or 'BRIEFING'
        current_phase = previous_phase
        transition_events: list[str] = []

        if previous_phase == 'BRIEFING' and any((item.get('compressionRate') or 0) > 0 for item in observations):
            current_phase = 'COMPRESSIONS'
            transition_events.append('compressions_started')

        started_at = session_state_in.get('startedAt') or now_ms
        current_cycle = session_state_in.get('currentCycle') or 1
        cycle_history = list(session_state_in.get('cycleHistory') or [])
        cycle_start_timestamp = runtime_state_in.get('cycleStartTimestamp')
        cycle_compression_count = runtime_state_in.get('cycleCompressionCount', 0)
        cycle_rates = list(runtime_state_in.get('cycleRates') or [])
        total_compression_time_ms = runtime_state_in.get('totalCompressionTimeMs', 0)
        last_compression_timestamp = runtime_state_in.get('lastCompressionTimestamp')
        was_compressing = runtime_state_in.get('wasCompressing', False)
        inter_compression_intervals = list(runtime_state_in.get('interCompressionIntervals') or [])
        last_counted_peak_timestamp = runtime_state_in.get('lastCountedPeakTimestamp', 0)
        compressions_since_ventilation = runtime_state_in.get('compressionsSinceVentilation', 0)
        ventilation_breath_count = runtime_state_in.get('ventilationBreathCount', 0)

        recent_peaks = [t for t in (observation.get('peakTimestamps') or []) if t > observation['timestamp'] - 2000]
        is_compressing = len(recent_peaks) > 0
        if is_compressing and was_compressing and last_compression_timestamp is not None:
            delta = observation['timestamp'] - last_compression_timestamp
            if 0 < delta < 2000:
                total_compression_time_ms += delta
        if is_compressing:
            last_compression_timestamp = observation['timestamp']
        was_compressing = is_compressing

        total_elapsed_ms = observations[-1]['timestamp'] - observations[0]['timestamp'] if len(observations) >= 2 else 0
        compression_fraction = min(1, total_compression_time_ms / total_elapsed_ms) if total_elapsed_ms > 0 else 0

        all_peaks = sorted(observation.get('peakTimestamps') or [])
        for idx in range(1, len(all_peaks)):
            if all_peaks[idx] > last_counted_peak_timestamp and all_peaks[idx - 1] > last_counted_peak_timestamp:
                interval = all_peaks[idx] - all_peaks[idx - 1]
                if 0 < interval < 3000:
                    inter_compression_intervals.append(interval)
                    if len(inter_compression_intervals) > 30:
                        inter_compression_intervals.pop(0)
        rate_consistency = self._compute_rate_consistency(inter_compression_intervals)

        if current_phase == 'COMPRESSIONS':
            if cycle_start_timestamp is None:
                cycle_start_timestamp = now_ms
            new_peaks = [t for t in (observation.get('peakTimestamps') or []) if t > last_counted_peak_timestamp]
            cycle_compression_count += len(new_peaks)
            if training_mode == 'CONVENTIONAL_30_2':
                compressions_since_ventilation += len(new_peaks)
            if new_peaks:
                last_counted_peak_timestamp = max(new_peaks)
            if is_compressing:
                cycle_rates.append(current_rate)

            if training_mode == 'CONVENTIONAL_30_2' and cycle_start_timestamp is not None:
                elapsed_cycle_seconds = (now_ms - cycle_start_timestamp) / 1000
                if elapsed_cycle_seconds >= CYCLE_DURATION_SECONDS:
                    duration_ms = now_ms - cycle_start_timestamp
                    cycle_history.append({
                        'cycleNumber': current_cycle,
                        'averageRate': round(sum(cycle_rates) / len(cycle_rates)) if cycle_rates else 0,
                        'rateConsistency': rate_consistency,
                        'compressionCount': cycle_compression_count,
                        'durationSeconds': round(duration_ms / 1000),
                    })
                    current_cycle += 1
                    cycle_start_timestamp = None
                    cycle_compression_count = 0
                    cycle_rates = []
                    compressions_since_ventilation = 0
                    current_phase = 'CYCLE_BREAK'
                    transition_events.append('cycle_break_started')
                elif compressions_since_ventilation >= COMPRESSIONS_PER_CYCLE_30_2:
                    current_phase = 'VENTILATION'
                    ventilation_breath_count = 0
                    transition_events.append('ventilation_started')

        recoil_obs = [item for item in observations if item.get('recoilComplete') is not None]
        recoil_ratio = (sum(1 for item in recoil_obs if item.get('recoilComplete')) / len(recoil_obs)) if recoil_obs else 0

        depth_obs = [item for item in observations if (item.get('depthProxy') or 0) > 0]
        depth_proxy_average = (sum(item.get('depthProxy', 0) for item in depth_obs) / len(depth_obs)) if depth_obs else 0

        risk_level = 'LOW'
        if visible_ratio < 0.45 or straight_arm_ratio < 0.45:
            risk_level = 'HIGH'
        elif current_rate > 0 and (current_rate < scenario['targetCompressionRate']['min'] or current_rate > scenario['targetCompressionRate']['max']):
            risk_level = 'MEDIUM'

        checklist = self._build_checklist(observations, current_phase, scenario)

        session_state = {
            'module': 'CPR',
            'status': 'RUNNING' if observations else 'IDLE',
            'startedAt': started_at,
            'scenarioId': scenario['id'],
            'currentPhase': current_phase,
            'currentRate': current_rate,
            'averageRate': average_rate,
            'maxRate': max_rate,
            'elapsedSeconds': round((observation['timestamp'] - observations[0]['timestamp']) / 1000) if observations else 0,
            'checklist': checklist,
            'visibleRatio': visible_ratio,
            'straightArmRatio': straight_arm_ratio,
            'centeredRatio': centered_ratio,
            'riskLevel': risk_level,
            'observations': observations,
            'trainingMode': training_mode,
            'currentCycle': current_cycle,
            'cycleHistory': cycle_history,
            'compressionFraction': compression_fraction,
            'rateConsistency': rate_consistency,
            'recoilRatio': recoil_ratio,
            'depthProxyAverage': depth_proxy_average,
            'compressionCount': cycle_compression_count,
        }

        runtime_state = {
            'cycleStartTimestamp': cycle_start_timestamp,
            'cycleCompressionCount': cycle_compression_count,
            'cycleRates': cycle_rates,
            'totalCompressionTimeMs': total_compression_time_ms,
            'lastCompressionTimestamp': last_compression_timestamp,
            'wasCompressing': was_compressing,
            'interCompressionIntervals': inter_compression_intervals,
            'lastCountedPeakTimestamp': last_counted_peak_timestamp,
            'compressionsSinceVentilation': compressions_since_ventilation,
            'ventilationBreathCount': ventilation_breath_count,
        }

        decision = self.decide(session_state)
        return self._build_result(session_state, runtime_state, decision, transition_events)

    def apply_action(self, scenario: dict[str, Any], state: dict[str, Any], action: str, phase: str | None = None) -> dict[str, Any]:
        session_state = dict((state or {}).get('sessionState') or {})
        runtime_state = dict((state or {}).get('runtimeState') or {})
        transition_events: list[str] = []
        current_phase = session_state.get('currentPhase', 'BRIEFING')

        if action == 'advance_phase' and phase:
            session_state['currentPhase'] = phase
            transition_events.append(f'phase_advanced:{phase}')
        elif action == 'confirm_ventilation':
            breaths = (runtime_state.get('ventilationBreathCount') or 0) + 1
            runtime_state['ventilationBreathCount'] = breaths
            transition_events.append(f'ventilation_breath_confirmed:{breaths}')
            if breaths >= 2:
                runtime_state['compressionsSinceVentilation'] = 0
                runtime_state['ventilationBreathCount'] = 0
                session_state['currentPhase'] = 'COMPRESSIONS'
                transition_events.append('ventilation_completed')
        elif action == 'confirm_phase_advance' and current_phase == 'CYCLE_BREAK':
            session_state['currentPhase'] = 'COMPRESSIONS'
            runtime_state['cycleStartTimestamp'] = int(time.time() * 1000)
            runtime_state['cycleCompressionCount'] = 0
            runtime_state['cycleRates'] = []
            transition_events.append('cycle_break_resumed')

        observations = list(session_state.get('observations') or [])
        session_state['checklist'] = self._build_checklist(observations, session_state.get('currentPhase', current_phase), scenario)
        decision = self.decide(session_state)
        return self._build_result(session_state, runtime_state, decision, transition_events)

    def decide(self, state: dict[str, Any]) -> dict[str, Any]:
        phase = state['currentPhase']
        if phase in ['BRIEFING', 'SCENE_SAFETY', 'CHECK_RESPONSE', 'CALL_FOR_HELP', 'CHECK_BREATHING', 'AED_PROMPT']:
            return {
                'message': PHASE_INSTRUCTIONS.get(phase, 'Follow the on-screen instructions.'),
                'rhythmStatus': 'WAITING',
                'formStatus': 'READY',
                'riskLevel': 'LOW',
                'canEvaluate': False,
                'phaseInstruction': PHASE_INSTRUCTIONS.get(phase),
            }
        if phase == 'VENTILATION':
            return {
                'message': PHASE_INSTRUCTIONS['VENTILATION'],
                'rhythmStatus': 'WAITING',
                'formStatus': 'READY',
                'riskLevel': 'LOW',
                'canEvaluate': False,
                'phaseInstruction': PHASE_INSTRUCTIONS['VENTILATION'],
            }
        if phase == 'CYCLE_BREAK':
            return {
                'message': PHASE_INSTRUCTIONS['CYCLE_BREAK'],
                'rhythmStatus': 'WAITING',
                'formStatus': 'READY',
                'riskLevel': 'LOW',
                'canEvaluate': False,
                'phaseInstruction': PHASE_INSTRUCTIONS['CYCLE_BREAK'],
            }
        if phase in ['ASSESSMENT', 'COMPLETED']:
            return {
                'message': 'Evaluating your performance...' if phase == 'ASSESSMENT' else 'Session complete. Review your results.',
                'rhythmStatus': 'WAITING',
                'formStatus': 'READY',
                'riskLevel': state['riskLevel'],
                'canEvaluate': True,
            }

        rhythm_status = 'WAITING'
        form_status = 'READY'
        message = 'Position yourself and begin compressions.'

        current_rate = state['currentRate']
        if current_rate > 0 and current_rate < 100:
            rhythm_status = 'SLOW'
            message = 'Press faster to reach guideline rhythm.'
        elif 100 <= current_rate <= 120:
            rhythm_status = 'GOOD'
            message = 'Good rhythm. Keep the cadence steady.'
        elif current_rate > 120:
            rhythm_status = 'FAST'
            message = 'Press slower. Avoid overshooting the target cadence.'

        if state['visibleRatio'] < 0.5:
            form_status = 'HANDS_HIDDEN'
            message = 'Hands are not visible enough for reliable tracking.'
        elif state['straightArmRatio'] < 0.55:
            form_status = 'ARMS_BENT'
            message = 'Keep arms straight and stack shoulders over hands.'
        elif state['centeredRatio'] < 0.55:
            form_status = 'OFF_CENTER'
            message = 'Re-center your hands over the sternum line.'
        elif current_rate > 0:
            form_status = 'GOOD'

        if form_status == 'GOOD' and rhythm_status == 'GOOD':
            if (state.get('recoilRatio') or 1) < 0.5:
                message = 'Allow full chest recoil between compressions.'
            elif (state.get('depthProxyAverage') or 0.5) < 0.3:
                message = 'Push harder — compressions appear too shallow.'
            elif (state.get('rateConsistency') or 100) < 60:
                message = 'Stabilize your rhythm — timing is inconsistent.'
            elif (state.get('compressionFraction') or 1) < 0.6 and state['elapsedSeconds'] > 10:
                message = 'Minimize pauses — keep compression fraction above 60%.'

        return {
            'message': message,
            'rhythmStatus': rhythm_status,
            'formStatus': form_status,
            'riskLevel': state['riskLevel'],
            'canEvaluate': state['elapsedSeconds'] >= 10 and any((item.get('compressionRate') or 0) > 0 for item in state.get('observations', [])),
        }

    def evaluate(
        self,
        state: dict[str, Any],
        scenario: dict[str, Any],
        rubric: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        guideline_context = self.guideline_rag.get_guideline_context(config=config)
        standards = guideline_context.standards

        target = scenario['targetCompressionRate']
        rate_min = int(standards.get('compression_rate_min', target['min']))
        rate_max = int(standards.get('compression_rate_max', target['max']))
        depth_cm_min = float(standards.get('depth_cm_min', 5.0))
        depth_cm_max = float(standards.get('depth_cm_max', 6.0))
        compression_fraction_min = float(standards.get('compression_fraction_min', 0.6))
        defib_guidance = str(standards.get('defibrillation_guidance', '')).strip()

        average_rate = state['averageRate']
        if average_rate == 0:
            rate_distance = 100
        elif average_rate < rate_min:
            rate_distance = rate_min - average_rate
        elif average_rate > rate_max:
            rate_distance = average_rate - rate_max
        else:
            rate_distance = 0
        rhythm_score = clamp(100 - rate_distance * 3)

        form_score = clamp(
            state['visibleRatio'] * 35 + state['straightArmRatio'] * 35 + state['centeredRatio'] * 30
        )

        checklist = state['checklist']
        readiness_score = clamp((len([item for item in checklist if item['completed']]) / max(1, len(checklist))) * 100)

        depth_proxy_raw = state.get('depthProxyAverage') or 0
        depth_proxy_min = max(0.2, (depth_cm_min / 5.0) * 0.3)
        depth_proxy_max = min(0.9, (depth_cm_max / 5.0) * 0.3)

        if depth_proxy_min <= depth_proxy_raw <= depth_proxy_max:
            depth_proxy_score = 100
        elif depth_proxy_raw < depth_proxy_min:
            depth_proxy_score = clamp((depth_proxy_raw / max(0.05, depth_proxy_min)) * 100)
        else:
            depth_proxy_score = clamp(100 - ((depth_proxy_raw - depth_proxy_max) / max(0.05, 1 - depth_proxy_max)) * 40)

        recoil_score = clamp((state.get('recoilRatio') or 0) * 100)
        cf_raw = state.get('compressionFraction') or 0
        compression_fraction_score = clamp(
            100 if cf_raw >= compression_fraction_min else (cf_raw / max(0.1, compression_fraction_min)) * 100
        )
        rate_consistency_score = clamp(state.get('rateConsistency') or 100)

        weights = rubric['weights']
        w_rhythm = weights.get('rhythm', 35)
        w_form = weights.get('form', 25)
        w_readiness = weights.get('readiness', 5)
        w_depth = weights.get('depthProxy', 10)
        w_recoil = weights.get('recoil', 10)
        w_cf = weights.get('compressionFraction', 10)
        w_rc = weights.get('rateConsistency', 5)
        total_weight = w_rhythm + w_form + w_readiness + w_depth + w_recoil + w_cf + w_rc

        total_score = round((
            rhythm_score * w_rhythm +
            form_score * w_form +
            readiness_score * w_readiness +
            depth_proxy_score * w_depth +
            recoil_score * w_recoil +
            compression_fraction_score * w_cf +
            rate_consistency_score * w_rc
        ) / total_weight)

        strengths = []
        gaps = []
        next_steps = []

        if rate_min <= average_rate <= rate_max:
            strengths.append(f'Compression cadence stayed within the guideline {rate_min}-{rate_max} CPM range.')
        else:
            gaps.append(f'Compression cadence did not stay in the target {rate_min}-{rate_max} CPM window.')
            next_steps.append('Use the metronome and stabilize your tempo before increasing force.')

        thresholds = rubric['thresholds']
        if state['straightArmRatio'] >= thresholds['straightArmRatio']:
            strengths.append('Arm alignment was stable for most tracked compressions.')
        else:
            gaps.append('Elbows bent too often, which weakens compression mechanics.')
            next_steps.append('Lock elbows and shift body weight directly over the hands.')

        if state['centeredRatio'] >= thresholds['centeredRatio']:
            strengths.append('Hand placement remained centered during the session.')
        else:
            gaps.append('Hand position drifted away from the center line.')
            next_steps.append('Rehearse hand placement before starting each repetition block.')

        if state['visibleRatio'] < thresholds['visibleRatio']:
            gaps.append('Camera framing reduced tracking confidence for part of the session.')
            next_steps.append('Reposition the camera so shoulders, elbows, and wrists stay in frame.')

        if depth_proxy_score < 70:
            gaps.append(f'Compressions appear too shallow. Guideline depth target is approximately {depth_cm_min:.1f}-{depth_cm_max:.1f} cm.')
            next_steps.append('Push harder with locked elbows, using body weight rather than arm strength.')
        elif depth_proxy_score >= 90:
            strengths.append('Compression depth proxy is within the adequate range.')

        if recoil_score < 70:
            gaps.append('Incomplete chest recoil detected between compressions.')
            next_steps.append('Lift your body weight fully between compressions to allow complete chest recoil.')
        elif recoil_score >= 80:
            strengths.append('Good chest recoil between compressions.')

        if compression_fraction_score < 70 and state['elapsedSeconds'] > 10:
            gaps.append(f'Compression fraction is below the recommended {round(compression_fraction_min * 100)}% threshold.')
            next_steps.append('Minimize interruptions and pauses during CPR.')
        elif compression_fraction_score >= 80:
            strengths.append(f'Compression fraction is above the recommended {round(compression_fraction_min * 100)}% minimum.')

        if rate_consistency_score < 60:
            gaps.append('Compression rate was inconsistent — timing varied significantly.')
            next_steps.append('Practice with a metronome at 110 BPM to develop a consistent rhythm.')
        elif rate_consistency_score >= 80:
            strengths.append('Compression rate was consistent throughout the session.')

        cycles = state.get('cycleHistory') or []
        if len(cycles) >= 2:
            first = cycles[0]
            last = cycles[-1]
            if last['averageRate'] < first['averageRate'] - 10:
                gaps.append(f"Compression rate declined from {first['averageRate']} CPM (cycle 1) to {last['averageRate']} CPM (cycle {last['cycleNumber']}).")
                next_steps.append('Focus on maintaining rate across cycles — fatigue management is key.')
            if last['rateConsistency'] < first['rateConsistency'] - 15:
                gaps.append('Rate consistency degraded in later cycles, suggesting fatigue.')
                next_steps.append('Practice longer drills to build endurance.')

        if not strengths:
            strengths.append('You completed a full tracked CPR repetition set.')
        if not next_steps:
            next_steps.append('Repeat the drill for 30 seconds and aim to keep both rhythm and form green throughout.')
        if defib_guidance:
            next_steps.append(f'Defibrillation strategy reminder: {defib_guidance}')

        evaluation = {
            'totalScore': total_score,
            'breakdown': {
                'rhythm': round(rhythm_score),
                'form': round(form_score),
                'readiness': round(readiness_score),
                'depthProxy': round(depth_proxy_score),
                'recoil': round(recoil_score),
                'compressionFraction': round(compression_fraction_score),
                'rateConsistency': round(rate_consistency_score),
            },
            'strengths': strengths,
            'gaps': gaps,
            'nextSteps': next_steps,
        }

        headline = 'CPR workflow is on target.' if total_score >= 85 else 'CPR workflow is functional with correctable gaps.' if total_score >= 70 else 'CPR workflow needs more guided practice.'
        parts = [
            f"Average cadence {state['averageRate'] or 0} CPM",
            f"visibility {round(state['visibleRatio'] * 100)}%",
            f"straight-arm consistency {round(state['straightArmRatio'] * 100)}%",
        ]
        if state.get('compressionFraction') is not None:
            parts.append(f"compression fraction {round(state['compressionFraction'] * 100)}%")
        if state.get('rateConsistency') is not None:
            parts.append(f"rate consistency {state['rateConsistency']}/100")
        if state.get('recoilRatio') is not None:
            parts.append(f"recoil {round(state['recoilRatio'] * 100)}%")
        summary = ', '.join(parts) + '.'

        breakdown = evaluation['breakdown']
        dimensions = [
            ('Rhythm', breakdown['rhythm'], f'Guideline target is {rate_min}-{rate_max} compressions per minute. Practice with a metronome near the middle of this range.'),
            ('Form', breakdown['form'], 'Focus on locking elbows, centering hands over the sternum, and keeping shoulders stacked over hands.'),
            ('Depth', breakdown.get('depthProxy', 100), f'Guideline depth target is approximately {depth_cm_min:.1f}-{depth_cm_max:.1f} cm. Use body weight, not arm strength.'),
            ('Recoil', breakdown.get('recoil', 100), 'Allow complete chest recoil between compressions. Lift your hands slightly to avoid leaning.'),
            ('Compression Fraction', breakdown.get('compressionFraction', 100), f'Minimize pauses to keep compression fraction above {round(compression_fraction_min * 100)}%.'),
            ('Rate Consistency', breakdown.get('rateConsistency', 100), 'A steady rhythm is more effective than varying speed. Use a metronome for pacing.'),
        ]
        weakest = min(dimensions, key=lambda item: item[1])
        focus_area = f'Focus area: {weakest[0]} ({weakest[1]}/100). {weakest[2]}'

        cycle_comparison = None
        if len(cycles) >= 2:
            lines = [f'Completed {len(cycles)} cycles:']
            for cycle in cycles:
                lines.append(f"  Cycle {cycle['cycleNumber']}: {cycle['averageRate']} CPM avg, {cycle['compressionCount']} compressions, consistency {cycle['rateConsistency']}/100")
            first = cycles[0]
            last = cycles[-1]
            rate_delta = last['averageRate'] - first['averageRate']
            if abs(rate_delta) > 5:
                lines.append(
                    f"Rate decreased by {abs(rate_delta)} CPM from cycle 1 to {last['cycleNumber']} — watch for fatigue." if rate_delta < 0
                    else f"Rate increased by {rate_delta} CPM — you may be speeding up under pressure."
                )
            else:
                lines.append('Rate was consistent across cycles — good endurance.')
            cycle_comparison = '\n'.join(lines)

        feedback = {
            'headline': headline,
            'summary': summary,
            'evaluation': evaluation,
            'cycleComparison': cycle_comparison,
            'focusArea': focus_area,
            'guidelineSummary': guideline_context.summary,
            'guidelineSource': guideline_context.source_url,
            'guidelineTitle': guideline_context.source_title,
        }
        return {
            'evaluation': evaluation,
            'feedback': feedback,
        }
