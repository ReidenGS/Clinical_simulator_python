from __future__ import annotations

from typing import Any


class InterviewEvaluateService:
    def __init__(self) -> None:
        self._evaluation_chain = None

    @property
    def evaluation_chain(self):
        if self._evaluation_chain is None:
            from app.llm.chains.evaluation_chain import InterviewEvaluationChain

            self._evaluation_chain = InterviewEvaluationChain()
        return self._evaluation_chain

    def score_deterministic(self, dimension_id: str, session_state: dict[str, Any]) -> dict[str, Any]:
        if dimension_id == 'info_gathering':
            coverage = session_state['overallCoverage']
            evidence = [
                f"{d['dimension']}: {', '.join(d['coveredItems'])} ({d['percentage']}%)"
                for d in session_state['dimensionCoverages']
                if d['coveredItems']
            ]
            if coverage >= 80:
                feedback = 'Excellent history taking -- comprehensive coverage across all key dimensions.'
            elif coverage >= 60:
                feedback = 'Good history taking with adequate coverage, but some areas could be explored further.'
            elif coverage >= 40:
                feedback = 'Partial history -- several important areas were not explored.'
            else:
                feedback = 'Incomplete history taking -- many critical areas were missed.'
            return {'rawScore': min(100, coverage), 'feedback': feedback, 'evidence': evidence}

        if dimension_id == 'efficiency':
            turns = session_state['turnCount']
            coverage = session_state['overallCoverage']
            ratio = (coverage / turns) if turns > 0 else 0
            if ratio >= 7:
                raw_score = 100
            elif ratio >= 5:
                raw_score = 85
            elif ratio >= 3:
                raw_score = 70
            elif ratio >= 2:
                raw_score = 55
            else:
                raw_score = 40
            if turns > 20:
                raw_score = max(30, raw_score - 15)
            feedback = f'You used {turns} turns to achieve {coverage}% coverage (efficiency ratio: {ratio:.1f}).'
            evidence = [f'{turns} turns', f'{coverage}% coverage', f'ratio: {ratio:.1f}']
            return {'rawScore': raw_score, 'feedback': feedback, 'evidence': evidence}

        return {'rawScore': 50, 'feedback': 'Unable to score this dimension deterministically.', 'evidence': []}

    def score_llm(self, dim: dict[str, Any], session_state: dict[str, Any], diagnosis: str, case_data: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        try:
            parsed = self.evaluation_chain.invoke(
                dim=dim,
                session_state=session_state,
                diagnosis=diagnosis,
                case_data=case_data,
                config=config,
            )
            return {
                'rawScore': parsed.raw_score,
                'feedback': parsed.feedback,
                'evidence': parsed.evidence,
            }
        except Exception:
            return {
                'rawScore': 50,
                'feedback': 'Evaluation unavailable for this dimension.',
                'evidence': [],
            }

    def determine_competency(self, weighted_score: int, thresholds: dict[str, int]) -> str:
        if weighted_score >= thresholds['expert']:
            return 'expert'
        if weighted_score >= thresholds['proficient']:
            return 'proficient'
        if weighted_score >= thresholds['competent']:
            return 'competent'
        if weighted_score >= thresholds['beginner']:
            return 'beginner'
        return 'novice'

    def recommend_next_case(self, result: dict[str, Any], current_difficulty: str, difficulty_cases: dict[str, list[dict[str, Any]]] | None, current_case_name: str | None = None) -> str | None:
        if current_difficulty not in {'easy', 'medium', 'hard'}:
            return None
        score = result['weightedTotal']
        if score >= 75 and current_difficulty == 'easy':
            next_difficulty = 'medium'
        elif score >= 75 and current_difficulty == 'medium':
            next_difficulty = 'hard'
        elif score < 40 and current_difficulty == 'hard':
            next_difficulty = 'medium'
        elif score < 40 and current_difficulty == 'medium':
            next_difficulty = 'easy'
        else:
            next_difficulty = current_difficulty
        if difficulty_cases and difficulty_cases.get(next_difficulty):
            # Skip the case the student just completed to avoid recommending the same one.
            candidates = [
                c for c in difficulty_cases[next_difficulty]
                if not current_case_name or c.get('name') != current_case_name
            ]
            # Fall back to full list if all same-difficulty cases are the current one.
            if not candidates:
                candidates = difficulty_cases[next_difficulty]
            next_case_name = candidates[0].get('name')
            if next_case_name:
                return f'Try "{next_case_name}" ({next_difficulty} difficulty) next.'
        return None

    def build_summary(self, level: str, score: int, case_data: dict[str, Any]) -> str:
        labels = {
            'novice': 'Novice',
            'beginner': 'Beginner',
            'competent': 'Competent',
            'proficient': 'Proficient',
            'expert': 'Expert',
        }
        tail = (
            'Well done! You demonstrated strong clinical skills.' if score >= 70 else
            'Good effort. Focus on the areas identified for improvement.' if score >= 50 else
            'This case was challenging. Review the feedback and try again with a systematic approach.'
        )
        return f'Your overall performance on the "{case_data["name"]}" case scored {score}/100, placing you at the {labels[level]} level. {tail}'

    def generate_feedback(self, rubric_result: dict[str, Any], case_data: dict[str, Any], rubric_config: dict[str, Any], difficulty_cases: dict[str, list[dict[str, Any]]] | None) -> dict[str, Any]:
        competency_level = self.determine_competency(rubric_result['weightedTotal'], rubric_config['competencyThresholds'])
        strengths = []
        areas = []
        recommendations = []
        for score in rubric_result['dimensionScores']:
            if score['rawScore'] >= 70:
                strengths.append(f"{score['dimensionName']}: {score['feedback']}")
            elif score['rawScore'] < 50:
                areas.append(f"{score['dimensionName']}: {score['feedback']}")
        weak_dimensions = sorted([d for d in rubric_result['dimensionScores'] if d['rawScore'] < 50], key=lambda x: x['rawScore'])
        for weak in weak_dimensions[:3]:
            if weak['dimensionId'] == 'info_gathering':
                recommendations.append('Practice using a systematic approach to history taking (e.g., SOCRATES for pain, ICE for patient perspective).')
            elif weak['dimensionId'] == 'clinical_reasoning':
                recommendations.append('Before each question, consider what differential it helps rule in or out.')
            elif weak['dimensionId'] == 'diagnostic_accuracy':
                recommendations.append('Review the key features that distinguish this condition from its common differentials.')
            elif weak['dimensionId'] == 'communication':
                recommendations.append('Practice using open-ended questions and acknowledging patient emotions before moving on.')
            elif weak['dimensionId'] == 'efficiency':
                recommendations.append('Try to ask fewer but more targeted questions. Avoid repeating topics already covered.')
            elif weak['dimensionId'] == 'safety':
                recommendations.append('Always screen for red flag symptoms early in the consultation.')
        return {
            'rubricResult': rubric_result,
            'competencyLevel': competency_level,
            'strengths': strengths,
            'areasForImprovement': areas,
            'specificRecommendations': recommendations,
            'nextCaseSuggestion': self.recommend_next_case(rubric_result, case_data.get('difficulty', ''), difficulty_cases, case_data.get('name')),
            'summary': self.build_summary(competency_level, rubric_result['weightedTotal'], case_data),
        }

    def evaluate(self, session_state: dict[str, Any], diagnosis: str, case_data: dict[str, Any], rubric_config: dict[str, Any], config: dict[str, Any], difficulty_cases: dict[str, list[dict[str, Any]]] | None = None) -> dict[str, Any]:
        dimension_scores = []
        for dim in rubric_config['dimensions']:
            if dim['scoringMethod'] == 'deterministic':
                result = self.score_deterministic(dim['id'], session_state)
            else:
                result = self.score_llm(dim, session_state, diagnosis, case_data, config)
            dimension_scores.append({
                'dimensionId': dim['id'],
                'dimensionName': dim['name'],
                'rawScore': result['rawScore'],
                'weight': dim['weight'],
                'weightedScore': result['rawScore'] * dim['weight'],
                'feedback': result['feedback'],
                'evidence': result['evidence'],
            })
        weighted_total = round(sum(d['weightedScore'] for d in dimension_scores))
        rubric_result = {
            'dimensionScores': dimension_scores,
            'weightedTotal': weighted_total,
            'maxScore': 100,
        }
        feedback_report = self.generate_feedback(rubric_result, case_data, rubric_config, difficulty_cases)
        return {
            'rubricResult': rubric_result,
            'feedbackReport': feedback_report,
        }
