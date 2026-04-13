from __future__ import annotations

import json
import math
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


@dataclass(frozen=True)
class _VectorEntry:
    diagnosis_key: str
    flags: list[str]
    weights: dict[str, float]
    norm: float


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
    _QUERY_ALIASES: dict[str, tuple[str, ...]] = {
        # Coronary / ACS
        'heart attack': ('myocardial infarction', 'acute coronary syndrome'),
        'mi': ('myocardial infarction',),
        'stemi': ('myocardial infarction', 'acute coronary syndrome'),
        'nstemi': ('myocardial infarction', 'acute coronary syndrome'),
        'acs': ('acute coronary syndrome',),
        'angina': ('acute coronary syndrome',),
        # Pulmonary embolism / DVT
        'blood clot in lung': ('pulmonary embolism',),
        'lung clot': ('pulmonary embolism',),
        'pe': ('pulmonary embolism',),
        'dvt': ('pulmonary embolism',),
        # Stroke / TIA
        'brain attack': ('stroke',),
        'cva': ('stroke',),
        'tia': ('stroke',),
        'transient ischaemic attack': ('stroke',),
        'transient ischemic attack': ('stroke',),
        # Respiratory
        'lung infection': ('pneumonia',),
        'chest infection': ('pneumonia',),
        'breathlessness': ('asthma', 'copd exacerbation'),
        'sob': ('asthma', 'copd exacerbation'),
        'shortness of breath': ('asthma', 'copd exacerbation'),
        'chronic obstructive': ('copd exacerbation',),
        # Sepsis
        'systemic infection': ('sepsis',),
        'bacteremia': ('sepsis',),
        'bacteraemia': ('sepsis',),
        'blood poisoning': ('sepsis',),
        'septicaemia': ('sepsis',),
        'septicemia': ('sepsis',),
    }
    _VECTOR_SCORE_THRESHOLD = 0.12

    def __init__(self) -> None:
        self.ai_service = self._build_ai_service()
        self.offline_rules = self._load_offline_rules()
        self._vector_index, self._idf = self._build_vector_index()

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

        vector_flags, vector_matched = self._vector_red_flags(diagnosis_hint)
        if vector_matched:
            return RedFlagContext(
                red_flags=vector_flags[:6],
                source_urls=[],
                source_mode='vector_offline',
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

    def _build_vector_index(self) -> tuple[list[_VectorEntry], dict[str, float]]:
        docs: list[tuple[str, list[str], list[str]]] = []
        df: dict[str, int] = {}
        for key, flags in self.offline_rules.items():
            doc_text = f'{key} ' + ' '.join(flags)
            tokens = self._tokenize(doc_text)
            if not tokens:
                continue
            docs.append((key, flags, tokens))
            for token in set(tokens):
                df[token] = df.get(token, 0) + 1

        total_docs = max(1, len(docs))
        idf = {token: math.log(1 + (total_docs / (1 + freq))) + 1 for token, freq in df.items()}

        entries: list[_VectorEntry] = []
        for key, flags, tokens in docs:
            tf: dict[str, float] = {}
            for token in tokens:
                tf[token] = tf.get(token, 0.0) + 1.0
            max_tf = max(tf.values()) if tf else 1.0
            weights = {token: (count / max_tf) * idf.get(token, 1.0) for token, count in tf.items()}
            norm = math.sqrt(sum(weight * weight for weight in weights.values()))
            entries.append(
                _VectorEntry(
                    diagnosis_key=key,
                    flags=list(flags),
                    weights=weights,
                    norm=norm,
                )
            )
        return entries, idf

    def _expand_query_text(self, diagnosis_hint: str) -> str:
        lowered = diagnosis_hint.strip().lower()
        expansions: list[str] = []
        for phrase, alias_targets in self._QUERY_ALIASES.items():
            if phrase in lowered:
                expansions.extend(alias_targets)
        if not expansions:
            return diagnosis_hint
        return f"{diagnosis_hint} {' '.join(expansions)}"

    def _vector_red_flags(self, diagnosis_hint: str) -> tuple[list[str], bool]:
        query = self._expand_query_text(diagnosis_hint)
        q_tokens = self._tokenize(query)
        if not q_tokens or not self._vector_index:
            return ([], False)

        # Build query TF-IDF vector (same scheme as document vectors)
        q_tf: dict[str, float] = {}
        for token in q_tokens:
            q_tf[token] = q_tf.get(token, 0.0) + 1.0
        q_max_tf = max(q_tf.values()) if q_tf else 1.0
        q_weights = {
            token: (count / q_max_tf) * self._idf.get(token, 1.0)
            for token, count in q_tf.items()
        }
        q_norm = math.sqrt(sum(w * w for w in q_weights.values()))
        if q_norm <= 0:
            return ([], False)

        best_score = 0.0
        best: _VectorEntry | None = None
        for entry in self._vector_index:
            if entry.norm <= 0:
                continue
            dot = sum(q_weights.get(token, 0.0) * entry.weights.get(token, 0.0) for token in q_weights)
            score = dot / (q_norm * entry.norm)
            if score > best_score:
                best_score = score
                best = entry

        if best is None or best_score < self._VECTOR_SCORE_THRESHOLD:
            return ([], False)
        return (best.flags, True)

    def _tokenize(self, text: str) -> list[str]:
        normalized = re.sub(r'[^a-z0-9 ]+', ' ', text.lower())
        tokens = [tok for tok in normalized.split() if len(tok) >= 2]
        return tokens

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
