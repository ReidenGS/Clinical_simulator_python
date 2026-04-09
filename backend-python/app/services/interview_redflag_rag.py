from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus


@dataclass(frozen=True)
class RedFlagContext:
    red_flags: list[str]
    source_urls: list[str]
    source_mode: str


class InterviewRedFlagRagService:
    """Offline-first red flag retrieval with controlled web fallback."""

    _ALLOWED_DOMAINS = (
        'nhs.uk',
        'cdc.gov',
        'medlineplus.gov',
        'mayoclinic.org',
        'heart.org',
        'who.int',
    )

    _DEFAULT_OFFLINE_RULES: dict[str, list[str]] = {
        'acute coronary syndrome': ['central chest pain lasting >15 minutes', 'pain radiating to arm, jaw, or back', 'shortness of breath at rest', 'syncope or near-syncope', 'cold sweat with persistent chest discomfort'],
        'myocardial infarction': ['persistent crushing chest pain', 'diaphoresis with nausea', 'hemodynamic instability or collapse', 'new severe dyspnea'],
        'pulmonary embolism': ['sudden pleuritic chest pain', 'acute dyspnea', 'hemoptysis', 'syncope', 'new unilateral leg swelling'],
        'stroke': ['sudden facial droop', 'sudden arm or leg weakness', 'new speech disturbance', 'sudden severe headache', 'new visual loss'],
        'sepsis': ['confusion or altered mental status', 'very fast breathing', 'systolic blood pressure < 90 mmHg', 'reduced urine output', 'mottled or cold peripheries'],
        'asthma': ['unable to speak full sentences', 'silent chest', 'cyanosis', 'drowsiness or exhaustion', 'poor response to rescue inhaler'],
        'copd exacerbation': ['severe breathlessness at rest', 'new cyanosis', 'confusion or drowsiness', 'inability to complete sentences', 'reduced consciousness'],
        'pneumonia': ['respiratory distress', 'confusion in older adults', 'oxygen saturation persistently low', 'hypotension or signs of sepsis', 'hemoptysis'],
    }

    def __init__(self) -> None:
        self.ai_service = self._build_ai_service()
        self.offline_rules = self._load_offline_rules()

    def _build_ai_service(self):
        try:
            from app.services.ai_service import AIService
        except Exception:
            return None
        return AIService()

    def get_red_flag_context(self, diagnosis_hint: str, difficulty: str, config: dict[str, Any]) -> RedFlagContext:
        offline, matched = self._offline_red_flags(diagnosis_hint)
        if matched:
            return RedFlagContext(
                red_flags=offline[:6],
                source_urls=[],
                source_mode='offline',
            )

        # Fallback path: only when offline rules have no diagnosis match.
        snippets = self._search_snippets(diagnosis_hint)

        llm_flags: list[str] = []
        if snippets:
            llm_flags = self._extract_with_llm(snippets, diagnosis_hint, difficulty, config)

        merged = self._merge_flags(llm_flags, offline)
        source_urls = [row['url'] for row in snippets if row.get('url')]

        if llm_flags and source_urls:
            mode = 'web+offline'
        elif source_urls:
            mode = 'web'
        else:
            mode = 'offline'

        return RedFlagContext(
            red_flags=merged[:6],
            source_urls=source_urls[:5],
            source_mode=mode,
        )

    _GENERIC_FLAGS = [
        'rapid symptom progression',
        'new confusion or reduced consciousness',
        'persistent severe pain unrelieved by rest',
        'shortness of breath at rest',
    ]

    def _offline_red_flags(self, diagnosis_hint: str) -> tuple[list[str], bool]:
        normalized = diagnosis_hint.strip().lower()
        for key, flags in self.offline_rules.items():
            if normalized and (key in normalized or normalized in key):
                return (list(flags), True)
        return (self._GENERIC_FLAGS, False)

    def _load_offline_rules(self) -> dict[str, list[str]]:
        path = Path(__file__).resolve().parents[2] / 'data' / 'redflags_offline.json'
        try:
            with path.open('r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return self._DEFAULT_OFFLINE_RULES
            loaded: dict[str, list[str]] = {}
            for key, values in data.items():
                if not isinstance(key, str) or not isinstance(values, list):
                    continue
                items = [str(v).strip() for v in values if str(v).strip()]
                if items:
                    loaded[key.strip().lower()] = items
            return loaded or self._DEFAULT_OFFLINE_RULES
        except Exception:
            return self._DEFAULT_OFFLINE_RULES

    def _search_snippets(self, diagnosis_hint: str) -> list[dict[str, str]]:
        try:
            import httpx

            query = f'{diagnosis_hint} red flag symptoms urgent warning signs'
            url = f'https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_html=1&skip_disambig=1'
            with httpx.Client(timeout=8, follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()
                payload = response.json()

            rows: list[dict[str, str]] = []

            def collect(items: list[dict[str, Any]]) -> None:
                for item in items:
                    text = str(item.get('Text') or '').strip()
                    first_url = str(item.get('FirstURL') or '').strip()
                    if text and first_url and self._is_allowed_url(first_url):
                        rows.append({
                            'title': text.split(' - ')[0].strip()[:160],
                            'snippet': text[:280],
                            'url': first_url,
                        })
                    nested = item.get('Topics')
                    if isinstance(nested, list):
                        collect(nested)

            related = payload.get('RelatedTopics')
            if isinstance(related, list):
                collect(related)

            return list({row['url']: row for row in rows}.values())[:6]
        except Exception:
            return []

    def _is_allowed_url(self, url: str) -> bool:
        try:
            lowered = url.lower()
            return any(domain in lowered for domain in self._ALLOWED_DOMAINS)
        except Exception:
            return False

    def _extract_with_llm(
        self,
        snippets: list[dict[str, str]],
        diagnosis_hint: str,
        difficulty: str,
        config: dict[str, Any],
    ) -> list[str]:
        system_prompt = (
            'You are a clinical safety reviewer. '
            'From trusted medical snippets, extract urgent red-flag symptoms only. '
            'Return JSON only with key redFlags as an array of short symptom phrases.'
        )
        if self.ai_service is None:
            return []
        user_payload = {
            'diagnosisHint': diagnosis_hint,
            'difficulty': difficulty,
            'trustedSnippets': snippets,
            'constraints': {
                'maxItems': 6,
                'minItems': 3,
                'style': 'symptom phrase only',
            },
        }

        try:
            raw = self.ai_service.generate_json(
                provider=config['textProvider'],
                system_prompt=system_prompt,
                messages=[{'role': 'user', 'content': json.dumps(user_payload, ensure_ascii=False)}],
                temperature=0.1,
                model=config.get('textModel'),
                api_key=config.get('textApiKey'),
                base_url=config.get('textBaseUrl'),
            )
            parsed = json.loads(raw)
            red_flags = parsed.get('redFlags')
            if not isinstance(red_flags, list):
                return []
            cleaned: list[str] = []
            for item in red_flags:
                text = re.sub(r'\s+', ' ', str(item or '')).strip()
                if text:
                    cleaned.append(text[:120])
            return cleaned[:6]
        except Exception:
            return []

    def _merge_flags(self, primary: list[str], secondary: list[str]) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for item in [*primary, *secondary]:
            norm = re.sub(r'[^a-z0-9 ]', '', item.lower()).strip()
            if not norm or norm in seen:
                continue
            seen.add(norm)
            merged.append(item)
        return merged
