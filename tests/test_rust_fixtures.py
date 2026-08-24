"""Rust 迁移期间由 Python oracle 与 Rust 共读的语言无关 fixture。"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

from onomedit.core.envvars import EnvContext, EnvVars, format_date
from onomedit.core.pathitem import PathItem
from onomedit.core.pipeline import diff_text, levenshtein
from onomedit.core.rules import apply_rule, rule_from_dict
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


def test_shared_rule_cases():
    for case in _fixture()["rules"]:
        assert apply_rule(case["value"], rule_from_dict(case["rule"])) == case["expected"]


def test_shared_template_sequences():
    for sequence in _fixture()["template_sequences"]:
        env = EnvVars()
        actual = []
        for item in sequence["inputs"]:
            context = EnvContext(clip_text=item.get("clip_text"))
            actual.append(env.expand(item["text"], context=context))
        assert actual == sequence["expected"]


def test_shared_date_formats():
    date = datetime.datetime(2026, 8, 12, 9, 5, 3, 123000)
    for case in _fixture()["date_formats"]:
        assert format_date(case["pattern"], date) == case["expected"]


def test_shared_diff_cases():
    for case in _fixture()["diffs"]:
        assert diff_text(case["left"], case["right"]) == case["expected"]
