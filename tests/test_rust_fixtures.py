"""Rust 迁移期间由 Python oracle 与 Rust 共读的语言无关 fixture。"""

from __future__ import annotations

import json
from pathlib import Path

from onomedit.core.pathitem import PathItem
from onomedit.core.pipeline import levenshtein
from onomedit.utils import transforms
from onomedit.utils.safename import sanitize_name


def _fixture() -> dict:
    path = Path(__file__).parents[1] / "tests-rust" / "fixtures" / "core.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_shared_safe_name_cases():
    for case in _fixture()["safe_names"]:
        assert sanitize_name(case["input"]) == case["expected"]


def test_shared_path_cases():
    for case in _fixture()["paths"]:
        item = PathItem(case["input"])
        assert item.name == case["name"]
        assert item.stem == case["stem"]
        assert item.ext == case["ext"]


def test_shared_transform_cases():
    for case in _fixture()["transforms"]:
        assert transforms.CONVERSIONS[case["kind"]](case["input"]) == case["expected"]


def test_shared_distance_cases():
    for case in _fixture()["distances"]:
        assert levenshtein(case["left"], case["right"]) == case["expected"]
