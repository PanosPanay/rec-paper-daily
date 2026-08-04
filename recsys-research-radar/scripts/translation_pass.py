#!/usr/bin/env python3
"""Apply and validate the Chinese translation pass for radar artifacts.

The fetcher deliberately keeps source text in English for verification. This
module is the small, deterministic bridge that lets the model translation pass
write Chinese fields back to the cards and experiment ideas before rendering.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


CARD_TRANSLATION_FIELDS = (
    "title_zh",
    "abstract_or_excerpt_zh",
    "core_contribution_zh",
    "methods_zh",
    "claims_zh",
    "limitations_zh",
    "future_directions_zh",
    "related_reading_zh",
    "datasets_or_benchmarks_zh",
    "recommended_action_zh",
    "deep_read_reason_zh",
    "possible_experiments_zh",
)

IDEA_TRANSLATION_FIELDS = (
    "title_zh",
    "hypothesis_zh",
    "observation_zh",
    "smallest_experiment_zh",
    "baseline_zh",
    "dataset_or_setup_zh",
    "metric_zh",
    "expected_runtime_zh",
    "failure_modes_zh",
)

_CJK_RE = re.compile(r"[\u3400-\u9fff]")


def has_chinese(value: Any) -> bool:
    """Return whether a translated value contains at least one CJK character."""

    if isinstance(value, str):
        return bool(_CJK_RE.search(value))
    if isinstance(value, list):
        return bool(value) and any(has_chinese(item) for item in value)
    if isinstance(value, dict):
        return any(has_chinese(item) for item in value.values())
    return False


def _field_required(record: dict[str, Any], field: str, source_field: str) -> bool:
    if field in {"title_zh", "recommended_action_zh", "deep_read_reason_zh"}:
        return bool(record.get(source_field))
    source = record.get(source_field)
    return bool(source)


def _translated_field_complete(record: dict[str, Any], field: str, source_field: str) -> bool:
    translated = record.get(field)
    source = record.get(source_field)
    if isinstance(source, list):
        if not isinstance(translated, list) or len(translated) < len(source):
            return False
        for source_item, translated_item in zip(source, translated):
            if isinstance(source_item, dict):
                if not isinstance(translated_item, dict):
                    return False
                if field == "related_reading_zh":
                    required = ("title_zh", "relation_zh")
                elif field == "possible_experiments_zh":
                    required = ("experiment_zh", "baseline_zh", "metric_zh")
                else:
                    required = tuple(key for key in translated_item if key.endswith("_zh"))
                if not required or any(not has_chinese(translated_item.get(key)) for key in required):
                    return False
            elif not has_chinese(translated_item):
                return False
        return True
    return has_chinese(translated)


def missing_translation_fields(cards: list[dict[str, Any]], ideas: list[dict[str, Any]]) -> list[dict[str, str]]:
    """List missing Chinese fields without treating empty optional source fields as gaps."""

    gaps: list[dict[str, str]] = []
    for card in cards:
        for field in CARD_TRANSLATION_FIELDS:
            source_field = field.removesuffix("_zh")
            if _field_required(card, field, source_field) and not _translated_field_complete(card, field, source_field):
                gaps.append({"kind": "card", "id": str(card.get("id", "")), "field": field})
    for index, idea in enumerate(ideas):
        for field in IDEA_TRANSLATION_FIELDS:
            source_field = field.removesuffix("_zh")
            if _field_required(idea, field, source_field) and not _translated_field_complete(idea, field, source_field):
                gaps.append({"kind": "idea", "id": str(index), "field": field})
    return gaps


def _as_translation_map(value: Any, key: str) -> dict[str, dict[str, Any]]:
    if isinstance(value, dict):
        return {
            str(item_key): item_value
            for item_key, item_value in value.items()
            if isinstance(item_value, dict)
        }
    if isinstance(value, list):
        result: dict[str, dict[str, Any]] = {}
        for index, item in enumerate(value):
            if not isinstance(item, dict):
                continue
            item_key = item.get(key) or item.get("id") or str(index)
            result[str(item_key)] = item
        return result
    return {}


def apply_translation_payload(
    cards: list[dict[str, Any]],
    ideas: list[dict[str, Any]],
    payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Merge a translation payload into generated cards and ideas in place."""

    card_translations = _as_translation_map(payload.get("cards", {}), "id")
    idea_translations = _as_translation_map(payload.get("ideas", {}), "source_item_id")
    for card in cards:
        translation = card_translations.get(str(card.get("id", "")), {})
        for field in CARD_TRANSLATION_FIELDS:
            if field in translation:
                card[field] = translation[field]
        card["translation_status"] = "translated" if not missing_translation_fields([card], []) else "needs_translation"

    for index, idea in enumerate(ideas):
        source_ids = idea.get("source_item_ids") or []
        translation = idea_translations.get(str(index), {})
        for source_id in source_ids:
            translation = translation or idea_translations.get(str(source_id), {})
        for field in IDEA_TRANSLATION_FIELDS:
            if field in translation:
                idea[field] = translation[field]

        source_card = next((card for card in cards if card.get("id") in source_ids), None)
        if source_card:
            if not has_chinese(idea.get("observation_zh")) and has_chinese(source_card.get("core_contribution_zh")):
                idea["observation_zh"] = source_card["core_contribution_zh"]
            if idea.get("title_zh") == "小实验：对应原文论文/文章" and has_chinese(source_card.get("title_zh")):
                idea["title_zh"] = "小实验：" + source_card["title_zh"]

    return cards, ideas


def build_translation_template(cards: list[dict[str, Any]], ideas: list[dict[str, Any]]) -> dict[str, Any]:
    """Create a compact template for the model to fill, retaining source IDs only."""

    return {
        "cards": {
            str(card.get("id", "")): {field: "" for field in CARD_TRANSLATION_FIELDS}
            for card in cards
        },
        "ideas": {
            str(index): {field: "" for field in IDEA_TRANSLATION_FIELDS}
            for index, _ in enumerate(ideas)
        },
    }


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply and validate radar Chinese translations.")
    parser.add_argument("--cards", type=Path, required=True)
    parser.add_argument("--ideas", type=Path, required=True)
    parser.add_argument("--translation-file", type=Path)
    parser.add_argument("--template", type=Path, help="Write a translation template instead of applying one.")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args(argv)

    cards = _read_json(args.cards)
    ideas = _read_json(args.ideas)
    if args.template:
        args.template.write_text(
            json.dumps(build_translation_template(cards, ideas), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return 0

    if not args.translation_file:
        parser.error("--translation-file is required unless --template is used")
    payload = _read_json(args.translation_file)
    apply_translation_payload(cards, ideas, payload)
    args.cards.write_text(json.dumps(cards, ensure_ascii=False, indent=2), encoding="utf-8")
    args.ideas.write_text(json.dumps(ideas, ensure_ascii=False, indent=2), encoding="utf-8")
    gaps = missing_translation_fields(cards, ideas)
    print(json.dumps({"translation_gaps": len(gaps), "gaps": gaps}, ensure_ascii=False, indent=2))
    return 3 if args.require_complete and gaps else 0


if __name__ == "__main__":
    raise SystemExit(main())
