import json
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import fetch_recsys_research as radar  # noqa: E402


ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2607.12345</id>
    <title>A Recommender System Test</title>
    <summary>We propose a recommender system ranking method.</summary>
    <published>2026-08-01T00:00:00Z</published>
    <author><name>Example Author</name></author>
    <category term="cs.IR" />
    <link title="pdf" type="application/pdf" href="https://arxiv.org/pdf/2607.12345" />
  </entry>
</feed>
"""


class ResearchRadarRegressionTests(unittest.TestCase):
    def test_arxiv_tries_a_mirror_after_primary_transport_failure(self):
        calls = []

        def fake_fetch(url, timeout=90.0, attempts=3):
            calls.append(url)
            if "export.arxiv.org" in url:
                raise URLError("temporary DNS failure")
            return ARXIV_XML.encode("utf-8")

        catalog = {"arxiv": {"categories": ["cs.IR"], "keywords": ["recommender system"]}}
        window_start = datetime(2026, 7, 31, tzinfo=timezone.utc)
        window_end = datetime(2026, 8, 3, tzinfo=timezone.utc)
        with patch.object(radar, "fetch_arxiv_bytes", side_effect=fake_fetch), patch.object(
            radar, "fetch_semantic_scholar", return_value=([], ["fallback disabled in test"])
        ):
            items, errors = radar.fetch_arxiv(catalog, 10, window_start, window_end)

        self.assertEqual(len(items), 1)
        self.assertTrue(any("arxiv.org/api/query" in url for url in calls))
        self.assertTrue(any("export.arxiv.org" in error for error in errors))

    def test_openreview_uses_api2_and_venue_id_with_access_token(self):
        calls = []

        def fake_fetch(url, timeout=30.0, headers=None):
            calls.append((url, headers or {}))
            return json.dumps(
                {
                    "notes": [
                        {
                            "id": "note-1",
                            "cdate": 1785542400000,
                            "content": {
                                "title": {"value": "Recommendation at a Conference"},
                                "abstract": {"value": "A public conference abstract."},
                                "authors": {"value": ["Example Author"]},
                            },
                        }
                    ]
                }
            ).encode("utf-8")

        catalog = {"openreview": {"venue_ids": ["ICLR.cc/2026/Conference"]}}
        with patch.dict(os.environ, {"OPENREVIEW_ACCESS_TOKEN": "test-token"}), patch.object(
            radar, "fetch_bytes", side_effect=fake_fetch
        ):
            items, errors = radar.fetch_openreview(
                catalog,
                10,
                datetime(2026, 7, 31, tzinfo=timezone.utc),
                datetime(2026, 8, 3, tzinfo=timezone.utc),
            )

        self.assertEqual(len(items), 1)
        self.assertIn("api2.openreview.net/notes", calls[0][0])
        self.assertIn("content.venue_id", calls[0][0])
        self.assertEqual(calls[0][1]["Cookie"], "openreview.accessToken=test-token")
        self.assertEqual(errors, [])

    def test_industry_section_renders_summary_not_only_a_link(self):
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
        card["abstract_or_excerpt_zh"] = "中文摘要：文章介绍了线上排序链路的质量与延迟权衡。"
        card["core_contribution_zh"] = "核心贡献：把排序质量和服务延迟放到同一个优化框架中。"
        report = radar.render_report(
            [card],
            [],
            [],
            {"manual": 1},
            "2026-08-03",
            "上一个工作日窗口",
            8,
            True,
        )

        self.assertIn("中文摘要：文章介绍了线上排序链路的质量与延迟权衡。", report)
        self.assertIn("核心贡献：把排序质量和服务延迟放到同一个优化框架中。", report)
        self.assertIn("原始链接", report)


if __name__ == "__main__":
    unittest.main()
