"""Language layer: an LLM may only (a) tag ambiguous narrations and (b) rewrite reason text.

It never alters a number: every number in generated text must equal a number in the template text,
otherwise the template text is used. The template provider is always available and is the default.
"""
from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from collections import Counter

import httpx

from app.core.config import get_settings
from app.i18n.templates import T, display_params, render

log = logging.getLogger("earnscore.language")

ALLOWED_TAGS = {"earned", "self_transfer", "refund", "loan", "other"}
_DIGITS = str.maketrans("०१२३४५६७८९௦௧௨௩௪௫௬௭௮௯", "01234567890123456789")
_NUM = re.compile(r"\d+(?:[.,]\d+)*")


def numbers_in(text: str) -> Counter:
    t = (text or "").translate(_DIGITS)
    return Counter(n.replace(",", "") for n in _NUM.findall(t))


def numbers_match(source: str, candidate: str) -> bool:
    return numbers_in(source) == numbers_in(candidate)


class LanguageProvider(ABC):
    name = "base"

    @abstractmethod
    def rewrite(self, text: str, lang: str) -> str | None: ...

    @abstractmethod
    def tag(self, narration: str) -> str | None: ...


class TemplateProvider(LanguageProvider):
    name = "template"

    def rewrite(self, text: str, lang: str) -> str | None:
        return None

    def tag(self, narration: str) -> str | None:
        return None


class GeminiProvider(LanguageProvider):
    name = "gemini"
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.cache: dict[tuple[str, str], str | None] = {}

    def _call(self, prompt: str) -> str | None:
        try:
            r = httpx.post(self.URL.format(model=self.model), params={"key": self.api_key}, timeout=8.0,
                           json={"contents": [{"parts": [{"text": prompt}]}],
                                 "generationConfig": {"temperature": 0.2, "maxOutputTokens": 200}})
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:  # network, quota, schema: fall back to templates
            log.info("gemini call failed", extra={"action": type(e).__name__})
            return None

    def rewrite(self, text: str, lang: str) -> str | None:
        key = (text, lang)
        if key not in self.cache:
            language = {"en": "English", "ta": "Tamil", "hi": "Hindi"}[lang]
            self.cache[key] = self._call(
                f"Rewrite this sentence for a gig worker in simple, warm {language}. Keep every number exactly as "
                f"written, add no new numbers or advice, and reply with the sentence only.\n\n{text}")
        return self.cache[key]

    def tag(self, narration: str) -> str | None:
        out = self._call("Classify this Indian bank credit narration as one of: earned, self_transfer, refund, loan, "
                         f"other. Reply with one word only.\n\n{json.dumps(narration)}")
        word = (out or "").strip().lower().strip(".")
        return word if word in ALLOWED_TAGS else None


_provider: LanguageProvider | None = None


def provider() -> LanguageProvider:
    global _provider
    if _provider is None:
        s = get_settings()
        if s.llm_provider == "gemini" and s.gemini_api_key:
            _provider = GeminiProvider(s.gemini_api_key, s.gemini_model)
        else:
            _provider = TemplateProvider()
    return _provider


def set_provider(p: LanguageProvider | None) -> None:
    global _provider
    _provider = p


def explain(code: str, params: dict, lang: str) -> dict:
    """Template text, optionally rewritten by the LLM if (and only if) all numbers survive unchanged."""
    template = render(code, display_params(code, params), lang)
    p = provider()
    text, source = template, "template"
    candidate = p.rewrite(template, lang)
    if candidate and numbers_match(template, candidate):
        text, source = candidate, p.name
    return {"text": text, "source": source}


def recourse_text(step: dict, from_band: str, lang: str) -> str:
    parts = []
    for c in step["changes"]:
        to = c["to"]
        if c["feature"] in {"on_time_rate", "active_week_share"}:
            to = round(to * 100)
        elif c["feature"] == "buffer_days":
            to = int(to)
        parts.append(render(f"STEP_{c['feature']}", {"to": to}, lang))
    actions = T["AND"][lang].join(parts)
    actions = actions[:1].upper() + actions[1:] if lang == "en" else actions
    return render("STEP_SENTENCE", {"actions": actions, "from_band": from_band, "to_band": step["new_band"]}, lang)


def sufficiency_message(features: dict, dsi: dict, lang: str) -> str:
    parts = dsi["parts"]
    gaps = {"months": 0.4 - parts["months"], "sources": 0.3 - parts["sources"], "reconcile_rate": 0.3 - parts["reconcile_rate"]}
    worst = max(gaps, key=gaps.get)
    if worst == "months":
        return render("NEED_MONTHS", {"months": str(int(features.get("months", 0)))}, lang)
    if worst == "sources":
        return render("NEED_SOURCES", {}, lang)
    return render("NEED_RECONCILE", {}, lang)


def tag_ambiguous(narration: str) -> str | None:
    """LLM tag for a narration the rules left unclassified; None means keep the rule result."""
    return provider().tag(narration)
