from __future__ import annotations

from typing import Any, Callable


class _DirectTool:
    """Fallback tool wrapper when langchain tool utilities are unavailable."""

    def __init__(self, fn: Callable[..., dict[str, Any]]) -> None:
        self._fn = fn

    def invoke(self, payload: Any) -> dict[str, Any]:
        if isinstance(payload, dict):
            return self._fn(**payload)
        return self._fn(payload)


def build_redflag_tools(
    offline_lookup: Callable[[str], dict[str, Any]],
    web_lookup: Callable[[str, str, dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    """Create LangChain tools for red-flag retrieval.

    The concrete retrieval logic is injected from the service layer so this module
    stays focused on tool contracts.
    """
    try:
        from langchain_core.tools import tool
    except Exception:
        return {
            'offline_red_flag_lookup': _DirectTool(
                lambda diagnosis_hint: offline_lookup(diagnosis_hint)
            ),
            'web_red_flag_search': _DirectTool(
                lambda diagnosis_hint, difficulty, provider, model='', api_key='', base_url='': web_lookup(
                    diagnosis_hint=diagnosis_hint,
                    difficulty=difficulty,
                    config={
                        'textProvider': provider,
                        'textModel': model or None,
                        'textApiKey': api_key or None,
                        'textBaseUrl': base_url or None,
                    },
                )
            ),
        }

    @tool('offline_red_flag_lookup')
    def offline_red_flag_lookup(diagnosis_hint: str) -> dict[str, Any]:
        return offline_lookup(diagnosis_hint)

    @tool('web_red_flag_search')
    def web_red_flag_search(
        diagnosis_hint: str,
        difficulty: str,
        provider: str,
        model: str = '',
        api_key: str = '',
        base_url: str = '',
    ) -> dict[str, Any]:
        return web_lookup(
            diagnosis_hint=diagnosis_hint,
            difficulty=difficulty,
            config={
                'textProvider': provider,
                'textModel': model or None,
                'textApiKey': api_key or None,
                'textBaseUrl': base_url or None,
            },
        )

    return {
        'offline_red_flag_lookup': offline_red_flag_lookup,
        'web_red_flag_search': web_red_flag_search,
    }
