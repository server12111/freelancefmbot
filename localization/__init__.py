import json
import os
from typing import Any

_translations: dict[str, dict] = {}
_locales_dir = os.path.dirname(__file__)


def _load(lang: str) -> dict:
    if lang not in _translations:
        path = os.path.join(_locales_dir, f"{lang}.json")
        with open(path, encoding="utf-8") as f:
            _translations[lang] = json.load(f)
    return _translations[lang]


class I18n:
    def __init__(self, lang: str = "en"):
        self.lang = lang
        self._data = _load(lang)

    def get(self, key: str, **kwargs: Any) -> str:
        text = self._data.get(key) or _load("en").get(key) or key
        if kwargs:
            try:
                text = text.format(**kwargs)
            except (KeyError, ValueError):
                pass
        return text

    def __call__(self, key: str, **kwargs: Any) -> str:
        return self.get(key, **kwargs)


def get_i18n(lang: str) -> I18n:
    return I18n(lang)
