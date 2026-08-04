import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import fetch_recsys_research as radar  # noqa: E402
from translation_pass import apply_translation_payload, missing_translation_fields  # noqa: E402


class TranslationPassTests(unittest.TestCase):
    def test_translation_payload_fills_required_card_fields(self):
        card = radar.score_item(
            radar.SourceItem(
                id="arxiv:test",
                source_type="arxiv",
                source_name="arXiv",
                title="A Ranking Method",
                authors=["Example"],
                summary="We propose a ranking method.",
                url="https://arxiv.org/abs/test",
                published="2026-08-03",
                categories=["cs.IR"],
            ),
            {"topic_groups": {}},
        )
        ideas = []
        payload = {
            "cards": {
                "arxiv:test": {
                    "title_zh": "一种排序方法",
                    "abstract_or_excerpt_zh": "本文提出一种排序方法。",
                    "core_contribution_zh": "核心贡献是改进排序建模。",
                    "methods_zh": ["学习排序"],
                    "recommended_action_zh": "持续跟踪",
                    "deep_read_reason_zh": "与排序问题相关，建议持续跟踪。",
                }
            },
            "ideas": {},
        }

        apply_translation_payload([card], ideas, payload)

        self.assertEqual(missing_translation_fields([card], ideas), [])
        self.assertEqual(card["translation_status"], "translated")

    def test_report_does_not_silently_fallback_to_english(self):
        card = radar.score_item(
            radar.SourceItem(
                id="industry:test",
                source_type="industry",
                source_name="Example Tech",
                title="Production Recommendation Ranking",
                authors=[],
                summary="A production ranking system improves quality and latency.",
                url="https://example.com/recommendation",
                published="2026-08-02",
                categories=["ranking"],
            ),
            {"topic_groups": {}},
        )
        report = radar.render_report(
            [card],
            [],
            [],
            {"industry": 1},
            "2026-08-03",
            "上一个工作日窗口",
            8,
            True,
        )

        self.assertIn("中文摘要待补充", report)
        self.assertIn("中文标题待补充", report)
        self.assertNotIn("摘要（原文摘要，待中文翻译）", report)
        self.assertNotIn("Found 1 new relevant", report)


if __name__ == "__main__":
    unittest.main()
