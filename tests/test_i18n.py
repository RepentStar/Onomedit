"""Language normalization, catalogs, and persisted language selection."""

from __future__ import annotations

import pytest

from onomedit import i18n
from onomedit.core import config


@pytest.fixture(autouse=True)
def _restore_language():
    previous = i18n.get_language()
    yield
    i18n.set_language(previous)


def test_supported_language_aliases_and_fallback():
    assert i18n.normalize_language("zh_CN") == "zh-CN"
    assert i18n.normalize_language("en_US") == "en-US"
    assert i18n.normalize_language("en") == "en-US"
    assert i18n.normalize_language("unknown") == "zh-CN"


def test_english_catalog_formats_values():
    i18n.set_language("en-US")
    assert i18n.tr("已添加 {added} 项，共 {total} 项", added=2, total=5) == (
        "Added 2 items; 5 total"
    )
    assert i18n.tr("就绪") == "Ready"


def test_config_persists_language(isolated_config):
    settings = config.default_config()
    assert settings.language == "zh-CN"
    config.set_value(settings, "language", "en-US")
    config.save_config(settings)
    assert config.load_config().language == "en-US"
    assert config.to_dict(settings)["language"] == "en-US"


def test_config_rejects_unsupported_language():
    with pytest.raises(ValueError, match="unsupported language"):
        config.set_value(config.default_config(), "language", "fr-FR")
