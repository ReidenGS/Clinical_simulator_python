from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from html import unescape
from typing import Any
from urllib.parse import quote_plus

from app.core.config import get_settings


GUIDELINE_URL = 'https://www.aclsmedicaltraining.com/blog/cpr-first-defibrillation-first'
DEFAULT_SEARCH_QUERY = 'CPR first defibrillation first high-quality CPR standards'


@dataclass(frozen=True)
class CprGuidelineContext:
    summary: str
    standards: dict[str, Any]
    source_url: str
    source_title: str
    fetched_at: int


class CprGuidelineRagService:
    """Search + read + summarize CPR guideline content for scoring alignment."""

    def __init__(self, cache_ttl_seconds: int = 6 * 60 * 60) -> None:
        self.settings = get_settings()
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cached: CprGuidelineContext | None = None
        self._ai_service = None

    def get_guideline_context(self, config: dict[str, Any] | None = None) -> CprGuidelineContext:
        now = int(time.time())
        if self._cached and now - self._cached.fetched_at <= self.cache_ttl_seconds:
            return self._cached

        search_results = self._search_web(DEFAULT_SEARCH_QUERY)
        page_text = self._fetch_webpage(GUIDELINE_URL)

        llm_payload = None
        if page_text:
            llm_payload = self._summarize_with_llm(page_text, search_results, config)

        if llm_payload:
            summary = str(llm_payload.get('summary') or '').strip()
            standards = self._normalize_standards(llm_payload.get('standards') or {})
            source_title = str(llm_payload.get('sourceTitle') or 'CPR First? Or Defibrillation First?').strip()
        else:
            summary = self._heuristic_summary(page_text)
            standards = self._default_standards()
            source_title = 'CPR First? Or Defibrillation First?'

        context = CprGuidelineContext(
            summary=summary,
            standards=standards,
            source_url=GUIDELINE_URL,
            source_title=source_title,
            fetched_at=now,
        )
        self._cached = context
        return context

    def _search_web(self, query: str) -> list[dict[str, str]]:
        """Tool: web_search(query)"""
        fallback = [
            {
                'title': 'CPR First? Or Defibrillation First?',
                'url': GUIDELINE_URL,
                'snippet': 'Discussion of CPR quality metrics and timing of first shock.',
            }
        ]

        try:
            import httpx

            url = f'https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_html=1&skip_disambig=1'
            with httpx.Client(timeout=10, follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()
                payload = response.json()

            results: list[dict[str, str]] = []

            def collect(items: list[dict[str, Any]]) -> None:
                for item in items:
                    if item.get('FirstURL') and item.get('Text'):
                        results.append({
                            'title': str(item.get('Text') or '').split(' - ')[0].strip()[:180],
                            'url': str(item.get('FirstURL') or '').strip(),
                            'snippet': str(item.get('Text') or '').strip()[:240],
                        })
                    nested = item.get('Topics')
                    if isinstance(nested, list):
                        collect(nested)

            related = payload.get('RelatedTopics')
            if isinstance(related, list):
                collect(related)

            dedup: dict[str, dict[str, str]] = {GUIDELINE_URL: fallback[0]}
            for row in results:
                row_url = row.get('url')
                if row_url:
                    dedup[row_url] = row

            return list(dedup.values())[:5]
        except Exception:
            return fallback

    def _fetch_webpage(self, url: str) -> str | None:
        """Tool: web_open(url)"""
        try:
            import httpx

            headers = {
                'User-Agent': 'Mozilla/5.0 (compatible; ClinicalSimulator/1.0; +https://example.local)'
            }
            with httpx.Client(timeout=15, follow_redirects=True, headers=headers) as client:
                response = client.get(url)
                response.raise_for_status()
                html = response.text

            html = re.sub(r'(?is)<script[^>]*>.*?</script>', ' ', html)
            html = re.sub(r'(?is)<style[^>]*>.*?</style>', ' ', html)
            text = re.sub(r'(?is)<[^>]+>', ' ', html)
            text = unescape(re.sub(r'\s+', ' ', text)).strip()
            return text[:30000]
        except Exception:
            return None

    def _get_ai_service(self):
        if self._ai_service is not None:
            return self._ai_service
        try:
            from app.services.ai_service import AIService
        except Exception:
            return None
        self._ai_service = AIService()
        return self._ai_service

    def _resolve_provider_config(self, config: dict[str, Any] | None) -> dict[str, Any] | None:
        if config and config.get('textProvider'):
            return {
                'provider': config.get('textProvider'),
                'model': config.get('textModel'),
                'api_key': config.get('textApiKey'),
                'base_url': config.get('textBaseUrl'),
            }

        if self.settings.openai_api_key:
            return {
                'provider': 'OPENAI',
                'model': self.settings.openai_model,
                'api_key': self.settings.openai_api_key,
                'base_url': self.settings.openai_base_url,
            }
        if self.settings.gemini_api_key:
            return {
                'provider': 'GEMINI',
                'model': self.settings.gemini_model,
                'api_key': self.settings.gemini_api_key,
                'base_url': None,
            }
        return None

    def _summarize_with_llm(
        self,
        page_text: str,
        search_results: list[dict[str, str]],
        config: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        ai_service = self._get_ai_service()
        provider_config = self._resolve_provider_config(config)
        if ai_service is None or provider_config is None:
            return None

        system_prompt = (
            'You are a CPR guideline analyst. Read the provided search results and web page content, then extract '
            'practical CPR scoring standards. Return JSON only with keys: summary, sourceTitle, standards. '
            'standards must include: compression_rate_min, compression_rate_max, depth_cm_min, depth_cm_max, '
            'compression_fraction_min, full_recoil_required, minimize_interruptions, avoid_excessive_ventilation, '
            'defibrillation_guidance.'
        )
        user_payload = {
            'search_results': search_results,
            'primary_url': GUIDELINE_URL,
            'page_content': page_text[:12000],
        }

        try:
            raw = ai_service.generate_json(
                provider=str(provider_config['provider']),
                system_prompt=system_prompt,
                messages=[{'role': 'user', 'content': json.dumps(user_payload, ensure_ascii=False)}],
                temperature=0.1,
                model=provider_config.get('model'),
                api_key=provider_config.get('api_key'),
                base_url=provider_config.get('base_url'),
            )
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                return None
            parsed['standards'] = self._normalize_standards(parsed.get('standards') or {})
            parsed['summary'] = str(parsed.get('summary') or '').strip()[:1200]
            if not parsed['summary']:
                return None
            return parsed
        except Exception:
            return None

    def _default_standards(self) -> dict[str, Any]:
        return {
            'compression_rate_min': 100,
            'compression_rate_max': 120,
            'depth_cm_min': 5.0,
            'depth_cm_max': 6.0,
            'compression_fraction_min': 0.6,
            'full_recoil_required': True,
            'minimize_interruptions': True,
            'avoid_excessive_ventilation': True,
            'defibrillation_guidance': 'Defibrillate as soon as practicable while maintaining continuous high-quality compressions during setup.',
        }

    def _normalize_standards(self, standards: dict[str, Any]) -> dict[str, Any]:
        defaults = self._default_standards()

        def as_float(key: str, low: float, high: float) -> float:
            try:
                value = float(standards.get(key, defaults[key]))
            except Exception:
                value = float(defaults[key])
            return max(low, min(high, value))

        normalized = {
            'compression_rate_min': int(as_float('compression_rate_min', 80, 140)),
            'compression_rate_max': int(as_float('compression_rate_max', 90, 150)),
            'depth_cm_min': as_float('depth_cm_min', 3.0, 7.0),
            'depth_cm_max': as_float('depth_cm_max', 4.0, 8.0),
            'compression_fraction_min': as_float('compression_fraction_min', 0.3, 0.9),
            'full_recoil_required': bool(standards.get('full_recoil_required', defaults['full_recoil_required'])),
            'minimize_interruptions': bool(standards.get('minimize_interruptions', defaults['minimize_interruptions'])),
            'avoid_excessive_ventilation': bool(standards.get('avoid_excessive_ventilation', defaults['avoid_excessive_ventilation'])),
            'defibrillation_guidance': str(standards.get('defibrillation_guidance', defaults['defibrillation_guidance'])).strip(),
        }

        if normalized['compression_rate_min'] >= normalized['compression_rate_max']:
            normalized['compression_rate_min'] = defaults['compression_rate_min']
            normalized['compression_rate_max'] = defaults['compression_rate_max']
        if normalized['depth_cm_min'] >= normalized['depth_cm_max']:
            normalized['depth_cm_min'] = defaults['depth_cm_min']
            normalized['depth_cm_max'] = defaults['depth_cm_max']

        if not normalized['defibrillation_guidance']:
            normalized['defibrillation_guidance'] = defaults['defibrillation_guidance']

        return normalized

    def _heuristic_summary(self, page_text: str | None) -> str:
        if not page_text:
            return (
                'High-quality CPR focuses on 100-120 compressions per minute, 5-6 cm depth, full chest recoil, '
                'minimal interruptions, and avoiding excessive ventilation. For witnessed shockable rhythms, '
                'defibrillation should be delivered as soon as practical while compressions continue during AED setup.'
            )

        lowered = page_text.lower()
        if 'defibrillation as soon as practicable' in lowered:
            return (
                'The reviewed guideline emphasizes high-quality CPR (100-120/min rate, 5-6 cm depth, full recoil, '
                'minimal interruptions, avoid excessive ventilation) and concludes that first shock should be given '
                'as soon as practical while continuing compressions during defibrillator setup.'
            )

        return (
            'The guideline highlights high-quality CPR fundamentals and supports rapid defibrillation with ongoing '
            'compressions during setup when treating shockable cardiac arrest.'
        )
