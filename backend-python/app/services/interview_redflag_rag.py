from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from app.tools import build_redflag_tools


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

    _OFFLINE_TOOL_NAME = 'offline_red_flag_lookup'
    _WEB_TOOL_NAME = 'web_red_flag_search'
    _SELF_CONFIDENCE_THRESHOLD = 0.75
    _SELF_MIN_FLAGS = 3

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
        self._tool_registry = self._build_tool_registry()

    def _build_ai_service(self):
        try:
            from app.services.ai_service import AIService
        except Exception:
            return None
        return AIService()

    def _build_tool_registry(self) -> dict[str, Any]:
        return build_redflag_tools(
            offline_lookup=self._tool_offline_lookup,
            web_lookup=self._tool_web_lookup,
        )

    def get_red_flag_context(self, diagnosis_hint: str, difficulty: str, config: dict[str, Any]) -> RedFlagContext:
        self_assessment = self._self_assess_with_llm(diagnosis_hint, difficulty, config)
        llm_self_flags = self._merge_flags(self_assessment.get('red_flags', []), [])
        self_confidence = float(self_assessment.get('confidence', 0.0) or 0.0)
        need_external = bool(self_assessment.get('need_external', True))

        if llm_self_flags and not need_external and (
            self_confidence >= self._SELF_CONFIDENCE_THRESHOLD or len(llm_self_flags) >= self._SELF_MIN_FLAGS
        ):
            return RedFlagContext(
                red_flags=llm_self_flags[:6],
                source_urls=[],
                source_mode='llm_self',
            )

        offline_result = self._invoke_tool_via_llm(
            tool_name=self._OFFLINE_TOOL_NAME,
            payload={'diagnosis_hint': diagnosis_hint},
            config=config,
        )
        offline_flags = self._merge_flags(llm_self_flags, offline_result.get('red_flags', []))

        if bool(offline_result.get('matched')):
            return RedFlagContext(
                red_flags=offline_flags[:6],
                source_urls=[],
                source_mode='offline' if not llm_self_flags else 'llm+offline',
            )
        if bool(offline_result.get('vector_matched')):
            return RedFlagContext(
                red_flags=offline_flags[:6],
                source_urls=[],
                source_mode='vector_offline' if not llm_self_flags else 'llm+vector_offline',
            )

        web_result = self._invoke_tool_via_llm(
            tool_name=self._WEB_TOOL_NAME,
            payload={
                'diagnosis_hint': diagnosis_hint,
                'difficulty': difficulty,
                'provider': str(config.get('textProvider', '')),
                'model': str(config.get('textModel', '') or ''),
                'api_key': str(config.get('textApiKey', '') or ''),
                'base_url': str(config.get('textBaseUrl', '') or ''),
            },
            config=config,
        )
        merged = self._merge_flags(offline_flags, web_result.get('red_flags', []))
        source_urls = [str(url) for url in web_result.get('source_urls', []) if str(url).strip()][:5]

        if web_result.get('red_flags') and source_urls:
            mode = 'web+offline'
        elif source_urls:
            mode = 'web'
        else:
            mode = 'offline'

        if not merged:
            merged = list(self._GENERIC_FLAGS)

        return RedFlagContext(
            red_flags=merged[:6],
            source_urls=source_urls,
            source_mode=mode,
        )

    _GENERIC_FLAGS = [
        'rapid symptom progression',
        'new confusion or reduced consciousness',
        'persistent severe pain unrelieved by rest',
        'shortness of breath at rest',
    ]

    def _self_assess_with_llm(self, diagnosis_hint: str, difficulty: str, config: dict[str, Any]) -> dict[str, Any]:
        if self.ai_service is None:
            return {'red_flags': [], 'confidence': 0.0, 'need_external': True}

        provider = str(config.get('textProvider', '')).strip()
        if not provider:
            return {'red_flags': [], 'confidence': 0.0, 'need_external': True}

        system_prompt = (
            'You are a clinical safety reviewer. '
            'Infer likely urgent red-flag symptoms from diagnosis hint only. '
            'Return JSON only with keys: redFlags (array of short phrases), confidence (0-1), needExternal (boolean).'
        )
        user_payload = {
            'diagnosisHint': diagnosis_hint,
            'difficulty': difficulty,
            'constraints': {
                'maxItems': 6,
                'minItems': 0,
                'style': 'symptom phrase only',
            },
        }

        try:
            raw = self.ai_service.generate_json(
                provider=provider,
                system_prompt=system_prompt,
                messages=[{'role': 'user', 'content': json.dumps(user_payload, ensure_ascii=False)}],
                temperature=0.0,
                model=config.get('textModel'),
                api_key=config.get('textApiKey'),
                base_url=config.get('textBaseUrl'),
            )
            parsed = json.loads(raw)
            return {
                'red_flags': self._clean_red_flags(parsed.get('redFlags')),
                'confidence': self._coerce_confidence(parsed.get('confidence')),
                'need_external': bool(parsed.get('needExternal', True)),
            }
        except Exception:
            return {'red_flags': [], 'confidence': 0.0, 'need_external': True}

    def _tool_offline_lookup(self, diagnosis_hint: str) -> dict[str, Any]:
        offline_flags, matched = self._offline_red_flags(diagnosis_hint)
        vector_flags: list[str] = []
        vector_matched = False
        if not matched:
            vector_flags, vector_matched = self._vector_red_flags(diagnosis_hint)
        red_flags = offline_flags if matched else (vector_flags if vector_matched else [])
        return {
            'red_flags': red_flags[:6],
            'source_urls': [],
            'matched': matched,
            'vector_matched': vector_matched,
        }

    def _tool_web_lookup(self, diagnosis_hint: str, difficulty: str, config: dict[str, Any]) -> dict[str, Any]:
        snippets = self._search_snippets(diagnosis_hint)

        llm_flags: list[str] = []
        if snippets:
            llm_flags = self._extract_with_llm(snippets, diagnosis_hint, difficulty, config)

        return {
            'red_flags': self._clean_red_flags(llm_flags)[:6],
            'source_urls': [row['url'] for row in snippets if row.get('url')][:5],
            'matched': bool(llm_flags),
            'vector_matched': False,
        }

    def _invoke_tool_via_llm(self, tool_name: str, payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        tool = self._tool_registry.get(tool_name)
        if tool is None:
            return self._invoke_tool_direct(tool_name, payload)

        if self.ai_service is None:
            return self._invoke_tool_direct(tool_name, payload)

        provider = str(config.get('textProvider', '')).strip()
        if not provider:
            return self._invoke_tool_direct(tool_name, payload)

        try:
            from langchain_core.messages import HumanMessage, SystemMessage
        except Exception:
            return self._invoke_tool_direct(tool_name, payload)

        try:
            chat_model = self.ai_service.factory.build_chat_model(
                provider=provider,
                temperature=0.0,
                model=config.get('textModel'),
                api_key=config.get('textApiKey'),
                base_url=config.get('textBaseUrl'),
            )
            bound = chat_model.bind_tools([tool])
            response = bound.invoke([
                SystemMessage(content='Call the provided tool exactly once with the JSON payload from the user message.'),
                HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
            ])
            tool_calls = getattr(response, 'tool_calls', None) or []
            if not tool_calls:
                return self._invoke_tool_direct(tool_name, payload)
            args = tool_calls[0].get('args')
            if not isinstance(args, dict):
                return self._invoke_tool_direct(tool_name, payload)
            return self._invoke_tool_direct(tool_name, args)
        except Exception:
            return self._invoke_tool_direct(tool_name, payload)

    def _invoke_tool_direct(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        tool = self._tool_registry.get(tool_name)
        if tool is None:
            return {}
        try:
            raw = tool.invoke(payload)
        except Exception:
            return {}

        if not isinstance(raw, dict):
            return {}
        return {
            'red_flags': self._clean_red_flags(raw.get('red_flags')),
            'source_urls': [str(url) for url in raw.get('source_urls', []) if str(url).strip()],
            'matched': bool(raw.get('matched', False)),
            'vector_matched': bool(raw.get('vector_matched', False)),
        }

    def _coerce_confidence(self, value: Any) -> float:
        try:
            score = float(value)
        except (TypeError, ValueError):
            return 0.0
        return min(1.0, max(0.0, score))

    def _clean_red_flags(self, red_flags: Any) -> list[str]:
        if not isinstance(red_flags, list):
            return []
        cleaned: list[str] = []
        for item in red_flags:
            text = re.sub(r'\s+', ' ', str(item or '')).strip()
            if text:
                cleaned.append(text[:120])
        return cleaned[:6]

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
        lowered = re.sub(r'[^a-z0-9 ]+', ' ', diagnosis_hint.strip().lower())
        token_set = set(lowered.split())
        expansions: list[str] = []
        for phrase, alias_targets in self._QUERY_ALIASES.items():
            if ' ' in phrase:
                if re.search(rf'\b{re.escape(phrase)}\b', lowered):
                    expansions.extend(alias_targets)
                continue
            if phrase in token_set:
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
            overlap_tokens = sum(1 for token in q_weights if token in entry.weights)
            if overlap_tokens < 2:
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
            return self._clean_red_flags(parsed.get('redFlags'))
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
