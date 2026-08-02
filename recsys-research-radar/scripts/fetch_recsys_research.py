#!/usr/bin/env python3
"""Fetch and summarize fresh recommender-system research signals.

This script is intentionally dependency-free. It fetches arXiv, OpenReview,
RSS/Atom feeds, and optional manual URLs, then converts items into structured
research cards, ranks them, generates small experiment ideas, and writes a
daily markdown report.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULT_CATALOG = SKILL_DIR / "references" / "source_catalog.json"
DEFAULT_OUTPUT_DIR = Path("/Users/wangbaojiang/Nutstore Files/我的坚果云/日常/推荐论文日报")

ARXIV_API = "https://export.arxiv.org/api/query"
OPENREVIEW_NOTES_API = "https://api.openreview.net/notes"
USER_AGENT = "RecSysResearchRadar/0.1 (local Codex skill; mailto:research@localhost)"
LOCAL_TZ = ZoneInfo("Asia/Shanghai")
TOPIC_LABELS_ZH = {
    "retrieval_candidate_generation": "召回与候选生成",
    "coarse_reranking": "粗排与重排",
    "ranking_learning_to_rank": "排序、粗排与重排",
    "sequential_user_modeling": "序列推荐与用户建模",
    "generative_llm_recommendation": "生成式/大模型推荐",
    "multimodal_recommendation": "多模态推荐",
    "graph_knowledge_social": "图与知识增强推荐",
    "bandit_rl_causal": "探索、强化学习与因果评估",
    "evaluation_debiasing_fairness": "评估、去偏与公平性",
    "systems_serving_infra": "服务、延迟与基础设施",
    "ads_marketplace": "广告与市场排序",
}
ACTION_ICONS = {
    "deep_read": "📖",
    "try_experiment": "🧪",
    "summarize": "📝",
    "track": "👀",
    "ignore": "⏸️",
}
RELATED_READING = {
    "retrieval_candidate_generation": [
        {"title": "Deep Neural Networks for YouTube Recommendations", "url": "https://research.google/pubs/deep-neural-networks-for-youtube-recommendations/", "relation": "经典的候选生成与排序两阶段工业架构"},
    ],
    "coarse_reranking": [
        {"title": "Deep Interest Network for Click-Through Rate Prediction", "url": "https://arxiv.org/abs/1706.06978", "relation": "工业 CTR 排序和用户兴趣建模的经典基线"},
    ],
    "sequential_user_modeling": [
        {"title": "Deep Interest Evolution Network for Click-Through Rate Prediction", "url": "https://arxiv.org/abs/1809.03672", "relation": "把用户兴趣演化引入序列行为建模"},
    ],
    "generative_llm_recommendation": [
        {"title": "GenRec: Towards LLM-Native Recommendation at Netflix", "url": "https://netflixtechblog.com/genrec-towards-llm-native-recommendation-at-netflix-f20be6f643e3", "relation": "业界大模型原生推荐架构实践"},
    ],
}


class HTTP308RedirectHandler(urllib.request.HTTPRedirectHandler):
    """urllib in older Python versions does not consistently follow HTTP 308."""

    def http_error_308(self, req, fp, code, msg, headers):  # type: ignore[no-untyped-def]
        return self.http_error_301(req, fp, code, msg, headers)

RECSYS_KEYWORDS = (
    "推荐系统",
    "推荐算法",
    "个性化推荐",
    "推荐广告",
    "搜索推荐",
    "搜推",
    "召回",
    "粗排",
    "精排",
    "排序模型",
    "生成式推荐",
    "大模型推荐",
    "用户兴趣",
    "recommend",
    "recommender",
    "recommendation",
    "personalization",
    "personalisation",
    "collaborative filtering",
    "ranking",
    "ranker",
    "retrieval",
    "candidate generation",
    "learning to rank",
    "session-based",
    "sequential recommendation",
    "two-tower",
    "dual encoder",
    "ctr",
    "cvr",
)

RECSYS_ANCHORS = (
    "推荐系统",
    "推荐算法",
    "个性化推荐",
    "推荐广告",
    "搜索推荐",
    "搜推",
    "召回",
    "排序",
    "生成式推荐",
    "大模型推荐",
    "recommender",
    "recommendation",
    "personalization",
    "personalisation",
    "collaborative filtering",
    "user-item",
    "item recommendation",
    "candidate generation",
    "ranking model",
    "industrial recommendation",
    "ctr",
    "cvr",
)

NOVELTY_CUES = (
    "we propose",
    "we introduce",
    "we present",
    "we develop",
    "novel",
    "new method",
    "new framework",
    "first",
    "state-of-the-art",
    "sota",
    "online experiment",
    "production",
)

CONTRIBUTION_CUES = (
    "we propose",
    "we introduce",
    "we present",
    "we develop",
    "we show",
    "we demonstrate",
    "this paper",
    "this work",
    "our approach",
    "our system",
)

CLAIM_CUES = (
    "outperform",
    "improve",
    "improves",
    "achieve",
    "achieves",
    "reduce",
    "reduces",
    "increase",
    "increases",
    "online experiment",
    "a/b test",
    "significant",
    "state-of-the-art",
    "better",
)

HARD_CUES = (
    "production-scale",
    "large-scale",
    "billion",
    "trillion",
    "multi-gpu",
    "distributed training",
    "proprietary",
    "online experiment",
    "real traffic",
    "industrial system",
)

EASY_CUES = (
    "movielens",
    "synthetic",
    "toy",
    "small",
    "offline",
    "benchmark",
    "public dataset",
    "ablation",
)

METHOD_CUES = (
    "collaborative filtering",
    "matrix factorization",
    "two-tower",
    "dual encoder",
    "transformer",
    "gnn",
    "graph neural network",
    "lightgcn",
    "contrastive learning",
    "reinforcement learning",
    "bandit",
    "causal",
    "counterfactual",
    "learning to rank",
    "reranking",
    "calibration",
    "distillation",
    "retrieval augmented generation",
    "rag",
    "llm",
)

DATASET_CUES = (
    "movielens",
    "amazon",
    "yelp",
    "mind",
    "kuairand",
    "kuairec",
    "gowalla",
    "lastfm",
    "steam",
    "taobao",
    "alibaba",
    "criteo",
    "avazu",
    "ml-1m",
    "ml-20m",
)

EXPERIMENT_TEMPLATES = {
    "retrieval_candidate_generation": {
        "experiment": "Compare a two-tower retrieval baseline against the proposed retrieval signal on a small implicit-feedback matrix.",
        "baseline": "matrix factorization or BM25-style popularity retrieval",
        "metric": "Recall@50, NDCG@50, and embedding build/query time",
    },
    "ranking_learning_to_rank": {
        "experiment": "Train a tiny reranker with and without the proposed feature/objective on a public click dataset subset.",
        "baseline": "logistic regression or LambdaMART-style ranking baseline",
        "metric": "NDCG@10, AUC, calibration error, and inference latency",
    },
    "coarse_reranking": {
        "experiment": "Compare a lightweight coarse ranker plus reranker cascade against a single-stage ranker on a small click dataset.",
        "baseline": "single-stage logistic regression or LambdaMART ranker",
        "metric": "Recall@K, NDCG@10, p95 latency, and candidate reduction ratio",
    },
    "sequential_user_modeling": {
        "experiment": "Test whether the sequence modeling change improves next-item prediction on MovieLens or synthetic sessions.",
        "baseline": "popularity, item-kNN, or SASRec-lite",
        "metric": "HitRate@10, NDCG@10, and cold-start breakdown",
    },
    "generative_llm_recommendation": {
        "experiment": "Evaluate a small LLM/RAG recommendation prompt against a non-generative retrieval/ranking pipeline on sampled items.",
        "baseline": "retrieval plus heuristic reranking",
        "metric": "NDCG@10, coverage, refusal/error rate, and cost per query",
    },
    "multimodal_recommendation": {
        "experiment": "Add lightweight image/text embeddings to an item retrieval baseline and measure lift on sparse users.",
        "baseline": "ID-only collaborative filtering",
        "metric": "Recall@20 and performance by user-history length",
    },
    "graph_knowledge_social": {
        "experiment": "Compare graph propagation depth against matrix factorization on a small user-item graph.",
        "baseline": "BPR-MF or LightGCN with one fixed depth",
        "metric": "NDCG@20, training time, and popularity bias",
    },
    "bandit_rl_causal": {
        "experiment": "Run an offline policy evaluation toy study for the proposed debiasing or exploration idea.",
        "baseline": "IPS/SNIPS or epsilon-greedy simulator",
        "metric": "estimated reward bias, variance, and regret in simulation",
    },
    "evaluation_debiasing_fairness": {
        "experiment": "Measure the proposed metric or debiasing trick on a small recommendation benchmark with popularity slices.",
        "baseline": "standard sampled offline evaluation",
        "metric": "NDCG@10, catalog coverage, Gini exposure, and slice lift",
    },
    "systems_serving_infra": {
        "experiment": "Prototype the serving optimization on a tiny retrieval/ranking service and measure speed-quality tradeoff.",
        "baseline": "unoptimized batch inference or exact search",
        "metric": "p95 latency, throughput, Recall@K, and memory footprint",
    },
    "ads_marketplace": {
        "experiment": "Simulate the ranking or auction change on synthetic marketplace logs with constrained diversity.",
        "baseline": "CTR-only ranking or second-price auction toy model",
        "metric": "utility, revenue proxy, exposure fairness, and conversion proxy",
    },
}


@dataclass
class SourceItem:
    id: str
    source_type: str
    source_name: str
    title: str
    authors: list[str]
    summary: str
    url: str
    published: str | None = None
    categories: list[str] | None = None


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def today_string() -> str:
    return datetime.now(LOCAL_TZ).date().isoformat()


def parse_as_of(value: str | None) -> datetime:
    if not value:
        return datetime.now(LOCAL_TZ)
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=LOCAL_TZ) if parsed.tzinfo is None else parsed.astimezone(LOCAL_TZ)


def compute_window(mode: str, lookback_days: int, as_of: str | None) -> tuple[datetime, datetime, str]:
    end_local = parse_as_of(as_of)
    if mode == "calendar":
        start_local = end_local - timedelta(days=lookback_days)
        label = f"最近 {lookback_days} 个自然日"
    else:
        previous_day = (end_local - timedelta(days=1)).date()
        if end_local.weekday() == 0:
            previous_day = (end_local - timedelta(days=3)).date()
            label = "上一个工作日及周末窗口"
        else:
            label = "上一个自然日窗口"
        start_local = datetime.combine(previous_day, datetime.min.time(), tzinfo=LOCAL_TZ)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc), label


def load_catalog(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"items": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"items": {}}


def apply_state(cards: list[dict[str, Any]], state: dict[str, Any]) -> None:
    records = state.setdefault("items", {})
    for card in cards:
        record = records.get(card["id"])
        card["is_repeat"] = bool(record)
        card["first_seen_at"] = record.get("first_seen_at") if record else card["discovered_at"]
        card["previously_reported"] = int(record.get("report_count", 0)) if record else 0


def update_state(cards: list[dict[str, Any]], state: dict[str, Any], run_at: str) -> None:
    records = state.setdefault("items", {})
    for card in cards:
        record = records.setdefault(card["id"], {"first_seen_at": run_at, "report_count": 0})
        record["last_seen_at"] = run_at
        record["report_count"] = int(record.get("report_count", 0)) + 1
        record["title"] = card["title"]
        record["url"] = card["url"]
        record["source_name"] = card["source_name"]
    state["updated_at"] = run_at


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_bytes(url: str, timeout: float = 30.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    opener = urllib.request.build_opener(HTTP308RedirectHandler)
    with opener.open(req, timeout=timeout) as resp:
        return resp.read()


def text_of(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict) and "value" in value:
        return text_of(value["value"])
    if isinstance(value, list):
        return ", ".join(text_of(v) for v in value)
    return html.unescape(str(value)).strip()


def normalize_space(value: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", value)).split())


def contains_keyword(text: str, keyword: str) -> bool:
    """Match keywords as phrases instead of arbitrary substrings.

    This avoids false positives such as "ann" matching "understanding".
    """
    keyword = keyword.lower().strip()
    if not keyword:
        return False
    pattern = r"(?<![a-z0-9])" + re.escape(keyword) + r"(?![a-z0-9])"
    return re.search(pattern, text) is not None


def make_id(prefix: str, value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return f"{prefix}:{slug[:96]}" if slug else f"{prefix}:{int(time.time())}"


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def within_window(value: str | None, window_start: datetime, window_end: datetime) -> bool:
    dt = parse_date(value)
    if dt is None:
        return True
    return window_start <= dt <= window_end


def build_arxiv_query(categories: list[str], keywords: list[str]) -> str:
    cats = " OR ".join(f"cat:{c}" for c in categories)
    kws = " OR ".join(f'all:"{k}"' for k in keywords)
    return f"({cats}) AND ({kws})"


def fetch_arxiv(catalog: dict[str, Any], max_results: int, window_start: datetime, window_end: datetime) -> tuple[list[SourceItem], list[str]]:
    cfg = catalog.get("arxiv", {})
    categories = cfg.get("categories", [])
    keywords = cfg.get("keywords", [])
    query = build_arxiv_query(categories, keywords)
    params = urllib.parse.urlencode(
        {
            "search_query": query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
    )
    url = f"{ARXIV_API}?{params}"
    errors: list[str] = []
    try:
        content = fetch_bytes(url)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return [], [f"arXiv fetch failed: {exc}"]

    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    root = ET.fromstring(content)
    items: list[SourceItem] = []
    for entry in root.findall("atom:entry", ns):
        title = normalize_space(entry.findtext("atom:title", default="", namespaces=ns))
        summary = normalize_space(entry.findtext("atom:summary", default="", namespaces=ns))
        entry_id = entry.findtext("atom:id", default="", namespaces=ns)
        arxiv_id = entry_id.rsplit("/", 1)[-1] if entry_id else make_id("arxiv", title)
        authors = [
            normalize_space(a.findtext("atom:name", default="", namespaces=ns))
            for a in entry.findall("atom:author", ns)
        ]
        authors = [a for a in authors if a]
        categories = [
            tag.attrib.get("term", "")
            for tag in entry.findall("atom:category", ns)
            if tag.attrib.get("term")
        ]
        published = entry.findtext("atom:published", default="", namespaces=ns) or None
        if not within_window(published, window_start, window_end):
            continue
        pdf_url = ""
        for link in entry.findall("atom:link", ns):
            if link.attrib.get("title") == "pdf" or link.attrib.get("type") == "application/pdf":
                pdf_url = link.attrib.get("href", "")
                break
        items.append(
            SourceItem(
                id=f"arxiv:{arxiv_id}",
                source_type="arxiv",
                source_name="arXiv",
                title=title,
                authors=authors,
                summary=summary,
                url=pdf_url or entry_id,
                published=published[:10] if published else None,
                categories=categories,
            )
        )
    return items, errors


def fetch_openreview(catalog: dict[str, Any], max_results: int, window_start: datetime, window_end: datetime) -> tuple[list[SourceItem], list[str]]:
    venue_ids = catalog.get("openreview", {}).get("venue_ids", [])
    items: list[SourceItem] = []
    errors: list[str] = []
    per_venue = max(1, max_results // max(1, len(venue_ids)))
    for venue_id in venue_ids:
        params = urllib.parse.urlencode({"content.venueid": venue_id, "limit": per_venue})
        url = f"{OPENREVIEW_NOTES_API}?{params}"
        try:
            payload = json.loads(fetch_bytes(url).decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            errors.append(f"OpenReview fetch failed for {venue_id}: {exc}")
            continue
        for note in payload.get("notes", []):
            content = note.get("content", {})
            title = normalize_space(text_of(content.get("title")))
            abstract = normalize_space(text_of(content.get("abstract")))
            authors = text_of(content.get("authors"))
            author_list = [a.strip() for a in authors.split(",") if a.strip()]
            cdate = note.get("cdate") or note.get("mdate")
            published = None
            if isinstance(cdate, (int, float)):
                published = datetime.fromtimestamp(cdate / 1000, timezone.utc).date().isoformat()
            if not within_window(published, window_start - timedelta(days=180), window_end):
                continue
            note_id = note.get("id", make_id("openreview", title))
            items.append(
                SourceItem(
                    id=f"openreview:{note_id}",
                    source_type="conference",
                    source_name=f"OpenReview {venue_id}",
                    title=title,
                    authors=author_list,
                    summary=abstract,
                    url=f"https://openreview.net/forum?id={note_id}",
                    published=published,
                    categories=[venue_id],
                )
            )
    return items, errors


def fetch_rss(catalog: dict[str, Any], max_results: int, window_start: datetime, window_end: datetime) -> tuple[list[SourceItem], list[str]]:
    feeds = catalog.get("rss_feeds", [])
    items: list[SourceItem] = []
    errors: list[str] = []
    per_feed = max(1, max_results // max(1, len(feeds)))
    for feed in feeds:
        name = feed.get("name", "RSS")
        url = feed.get("url", "")
        source_type = feed.get("source_type", "industry")
        try:
            root = ET.fromstring(fetch_bytes(url))
        except (urllib.error.URLError, TimeoutError, OSError, ET.ParseError) as exc:
            errors.append(f"RSS fetch failed for {name}: {exc}")
            continue
        feed_items = parse_feed_entries(root, name, source_type)
        kept = 0
        for item in feed_items:
            if kept >= per_feed:
                break
            if not within_window(item.published, window_start, window_end):
                continue
            haystack = f"{item.title}\n{item.summary}".lower()
            if not any(contains_keyword(haystack, k) for k in RECSYS_KEYWORDS):
                continue
            items.append(item)
            kept += 1
    return items, errors


def parse_feed_entries(root: ET.Element, source_name: str, source_type: str) -> list[SourceItem]:
    out: list[SourceItem] = []
    channel = root.find("channel")
    if channel is not None:
        for item in channel.findall("item"):
            title = normalize_space(item.findtext("title", default=""))
            summary = normalize_space(
                item.findtext("description", default="")
                or item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded", default="")
            )
            link = normalize_space(item.findtext("link", default=""))
            published = item.findtext("pubDate", default="") or None
            out.append(
                SourceItem(
                    id=make_id(source_name.lower(), link or title),
                    source_type=source_type,
                    source_name=source_name,
                    title=title,
                    authors=[],
                    summary=summary,
                    url=link,
                    published=published,
                    categories=[],
                )
            )
        return out

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall("atom:entry", ns):
        title = normalize_space(entry.findtext("atom:title", default="", namespaces=ns))
        summary = normalize_space(
            entry.findtext("atom:summary", default="", namespaces=ns)
            or entry.findtext("atom:content", default="", namespaces=ns)
        )
        link = ""
        for node in entry.findall("atom:link", ns):
            if node.attrib.get("href"):
                link = node.attrib["href"]
                break
        published = (
            entry.findtext("atom:published", default="", namespaces=ns)
            or entry.findtext("atom:updated", default="", namespaces=ns)
            or None
        )
        out.append(
            SourceItem(
                id=make_id(source_name.lower(), link or title),
                source_type=source_type,
                source_name=source_name,
                title=title,
                authors=[],
                summary=summary,
                url=link,
                published=published,
                categories=[],
            )
        )
    return out


def fetch_manual_urls(catalog: dict[str, Any], lookback_days: int) -> tuple[list[SourceItem], list[str]]:
    items: list[SourceItem] = []
    errors: list[str] = []
    for raw in catalog.get("manual_urls", []):
        url = raw.get("url") if isinstance(raw, dict) else str(raw)
        name = raw.get("name", "Manual URL") if isinstance(raw, dict) else "Manual URL"
        source_type = raw.get("source_type", "manual") if isinstance(raw, dict) else "manual"
        try:
            page = fetch_bytes(url).decode("utf-8", errors="ignore")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            errors.append(f"Manual URL fetch failed for {url}: {exc}")
            continue
        title_match = re.search(r"<title[^>]*>(.*?)</title>", page, flags=re.I | re.S)
        title = normalize_space(title_match.group(1)) if title_match else url
        text = normalize_space(page)
        if not any(contains_keyword(f"{title}\n{text}".lower(), k) for k in RECSYS_KEYWORDS):
            continue
        items.append(
            SourceItem(
                id=make_id("manual", url),
                source_type=source_type,
                source_name=name,
                title=title,
                authors=[],
                summary=text[:1200],
                url=url,
                published=None,
                categories=[],
            )
        )
    return items, errors


def sentence_split(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def clamp_score(value: float) -> float:
    return round(max(0.0, min(5.0, value)), 1)


def match_topics(text: str, topic_groups: dict[str, Any]) -> tuple[list[str], list[str], float]:
    matched: list[str] = []
    keywords: list[str] = []
    weight = 0.0
    for group_id, cfg in topic_groups.items():
        hits = [kw for kw in cfg.get("keywords", []) if contains_keyword(text, kw)]
        if hits:
            matched.append(group_id)
            keywords.extend(hits[:3])
            weight += float(cfg.get("weight", 1.0))
    return matched, keywords, weight


def extract_contribution(title: str, summary: str) -> str:
    sentences = sentence_split(summary)
    for s in sentences:
        if any(cue in s.lower() for cue in CONTRIBUTION_CUES):
            return shorten(s, 260)
    if sentences:
        return shorten(sentences[0], 260)
    return shorten(title, 260)


def extract_claims(summary: str, limit: int = 4) -> list[str]:
    claims: list[str] = []
    for s in sentence_split(summary):
        if any(cue in s.lower() for cue in CLAIM_CUES):
            claims.append(shorten(s, 240))
        if len(claims) >= limit:
            break
    return claims


def extract_limitations(summary: str, limit: int = 3) -> list[str]:
    cues = ("limitation", "limitations", "however", "challenge", "cost", "future work", "remain")
    return [shorten(s, 240) for s in sentence_split(summary) if any(cue in s.lower() for cue in cues)][:limit]


def extract_future_directions(summary: str, limit: int = 3) -> list[str]:
    cues = ("future", "we leave", "further", "promising", "could", "will explore", "next")
    return [shorten(s, 240) for s in sentence_split(summary) if any(cue in s.lower() for cue in cues)][:limit]


def build_related_reading(matched_topics: list[str]) -> list[dict[str, str]]:
    related: list[dict[str, str]] = []
    seen: set[str] = set()
    for topic in matched_topics:
        for item in RELATED_READING.get(topic, []):
            if item["url"] in seen:
                continue
            seen.add(item["url"])
            related.append(item)
            if len(related) >= 3:
                return related
    return related


def extract_methods(text: str, matched_keywords: list[str], limit: int = 6) -> list[str]:
    methods: list[str] = []
    seen: set[str] = set()
    for kw in matched_keywords + [cue for cue in METHOD_CUES if contains_keyword(text, cue)]:
        norm = kw.lower().strip()
        if norm and norm not in seen:
            seen.add(norm)
            methods.append(norm)
        if len(methods) >= limit:
            break
    return methods


def extract_datasets(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for cue in DATASET_CUES:
        if contains_keyword(text, cue) and cue not in seen:
            seen.add(cue)
            found.append(cue)
    return found


def shorten(value: str, width: int) -> str:
    value = normalize_space(value)
    if len(value) <= width:
        return value
    return value[: max(0, width - 3)].rstrip() + "..."


def score_item(item: SourceItem, catalog: dict[str, Any]) -> dict[str, Any]:
    topic_groups = catalog.get("topic_groups", {})
    text = f"{item.title}\n{item.summary}\n{' '.join(item.categories or [])}".lower()
    matched_topics, matched_keywords, topic_weight = match_topics(text, topic_groups)
    categories = [c.lower() for c in item.categories or []]
    has_recsys_anchor = any(contains_keyword(text, anchor) for anchor in RECSYS_ANCHORS)

    relevance = 0.0
    if matched_topics:
        relevance = 0.8 + topic_weight * 0.55
    if item.source_type == "arxiv" and "cs.ir" in categories:
        relevance += 0.4
    if item.source_type in {"conference", "industry"} and matched_topics:
        relevance += 0.3
    if item.source_type == "arxiv" and not has_recsys_anchor:
        relevance -= 1.7
    relevance = clamp_score(relevance)

    novelty = 1.0 + sum(0.45 for cue in NOVELTY_CUES if cue in text)
    if item.source_type == "industry" and any(c in text for c in ("production", "online", "a/b")):
        novelty += 0.6
    if any(c in text for c in ("survey", "review", "tutorial")):
        novelty = min(novelty, 1.5)
    novelty = clamp_score(novelty)

    difficulty = 2.2 + sum(0.55 for cue in HARD_CUES if cue in text)
    difficulty -= sum(0.35 for cue in EASY_CUES if cue in text)
    if item.source_type == "industry":
        difficulty += 0.4
    difficulty = clamp_score(difficulty)

    experimentability = 1.0 if matched_topics else 0.0
    if extract_datasets(text) or any(cue in text for cue in EASY_CUES):
        experimentability += 1.0
    if difficulty <= 2.5:
        experimentability += 0.7
    experimentability = clamp_score(experimentability)

    is_historical = item.source_type.startswith("historical")
    source_signal = 1.0 if item.source_type in {"conference", "industry"} else 0.5
    priority = (
        relevance * 0.45
        + novelty * 0.30
        + source_signal * 0.10
        + experimentability * 0.15
        - difficulty * 0.12
    )

    if relevance < 1.0:
        action = "ignore"
    elif relevance >= 4.0 and experimentability >= 2.0 and difficulty <= 3.2:
        action = "try_experiment"
    elif relevance >= 3.6 and novelty >= 2.6:
        action = "deep_read"
    elif relevance >= 2.2:
        action = "summarize"
    else:
        action = "track"

    experiments = []
    for topic in matched_topics[:3]:
        template = EXPERIMENT_TEMPLATES.get(topic)
        if template:
            experiments.append(template)

    evidence = []
    if matched_keywords:
        evidence.append("matched keywords: " + ", ".join(sorted(set(matched_keywords))[:8]))
    if item.categories:
        evidence.append("categories/venue: " + ", ".join(item.categories[:4]))

    return {
        "id": item.id,
        "source_type": item.source_type,
        "is_historical": is_historical,
        "source_name": item.source_name,
        "title": item.title,
        "title_zh": "",
        "authors": item.authors,
        "author_affiliations": [],
        "author_affiliations_confidence": "unknown",
        "published": item.published,
        "discovered_at": now_iso(),
        "url": item.url,
        "abstract_or_excerpt": shorten(item.summary, 1200),
        "abstract_or_excerpt_zh": "",
        "core_contribution": extract_contribution(item.title, item.summary),
        "core_contribution_zh": "",
        "methods": extract_methods(text, matched_keywords),
        "methods_zh": [],
        "claims": extract_claims(item.summary),
        "claims_zh": [],
        "limitations": extract_limitations(item.summary),
        "limitations_zh": [],
        "future_directions": extract_future_directions(item.summary),
        "future_directions_zh": [],
        "related_reading": build_related_reading(matched_topics),
        "related_reading_zh": [],
        "datasets_or_benchmarks": extract_datasets(text),
        "datasets_or_benchmarks_zh": [],
        "matched_topics": matched_topics,
        "relevance_score": relevance,
        "novelty_score": novelty,
        "implementation_difficulty": difficulty,
        "experimentability_score": experimentability,
        "priority_score": round(priority, 3),
        "recommended_action": action,
        "recommended_action_zh": "",
        "deep_read_reason": build_deep_read_reason(relevance, novelty, difficulty, matched_topics),
        "deep_read_reason_zh": "",
        "possible_experiments": experiments,
        "possible_experiments_zh": [],
        "translation_status": "pending_model_translation",
        "evidence": evidence,
        "fetched_at": now_iso(),
    }


def build_deep_read_reason(
    relevance: float, novelty: float, difficulty: float, matched_topics: list[str]
) -> str:
    if not matched_topics:
        return "No strong recommendation-topic match found."
    reasons = [f"matches {', '.join(matched_topics[:3])}"]
    if relevance >= 3.5:
        reasons.append("high relevance")
    if novelty >= 3.0:
        reasons.append("clear novelty cues")
    if difficulty <= 3.0:
        reasons.append("small experiment appears plausible")
    return "; ".join(reasons) + f" (difficulty {difficulty}/5)."


def dedupe_items(items: list[SourceItem]) -> list[SourceItem]:
    seen: set[str] = set()
    out: list[SourceItem] = []
    for item in items:
        key = re.sub(r"\W+", "", item.title.lower())[:160] or item.url
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def build_ideas(cards: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    ideas: list[dict[str, Any]] = []
    for card in cards:
        if card["recommended_action"] not in {"try_experiment", "deep_read", "summarize"}:
            continue
        experiments = card.get("possible_experiments") or []
        if not experiments:
            continue
        template = experiments[0]
        title = card["title"]
        ideas.append(
            {
                "title": "Mini test: " + shorten(title, 80),
                "title_zh": "",
                "source_item_ids": [card["id"]],
                "hypothesis": (
                    "The method or signal described in the source item improves at least one "
                    "offline recommendation metric over a simple baseline on a small dataset."
                ),
                "hypothesis_zh": "",
                "observation": shorten(card.get("core_contribution", ""), 300),
                "smallest_experiment": template["experiment"],
                "smallest_experiment_zh": "",
                "baseline": template["baseline"],
                "baseline_zh": "",
                "dataset_or_setup": choose_dataset(card),
                "dataset_or_setup_zh": "",
                "metric": template["metric"],
                "metric_zh": "",
                "expected_runtime": "< 30 minutes on a laptop CPU for a toy version",
                "failure_modes": [
                    "offline metric lift does not reproduce",
                    "gain appears only on popularity-heavy users/items",
                    "added complexity increases latency or instability",
                ],
                "failure_modes_zh": [],
                "novelty_score": card["novelty_score"],
                "feasibility_score": clamp_score(5.0 - card["implementation_difficulty"] + 1.0),
            }
        )
        if len(ideas) >= limit:
            break
    return ideas


def choose_dataset(card: dict[str, Any]) -> str:
    datasets = card.get("datasets_or_benchmarks") or []
    if datasets:
        return datasets[0]
    topics = set(card.get("matched_topics") or [])
    if "sequential_user_modeling" in topics:
        return "MovieLens-1M converted to user sequences, or synthetic sessions"
    if "multimodal_recommendation" in topics:
        return "Amazon review subset with text metadata, or a tiny image/text item catalog"
    if "bandit_rl_causal" in topics:
        return "synthetic logged bandit feedback with known propensities"
    return "MovieLens-small or a synthetic implicit-feedback matrix"


def render_report(
    cards: list[dict[str, Any]],
    ideas: list[dict[str, Any]],
    errors: list[str],
    counts: dict[str, int],
    output_date: str,
    window_label: str,
    report_limit: int,
    include_seen: bool,
) -> str:
    def score_line(card: dict[str, Any]) -> str:
        return (
            "🔎 相关性 " + str(card["relevance_score"])
            + " · ✨ 新颖性 " + str(card["novelty_score"])
            + " · 🧩 难度 " + str(card["implementation_difficulty"])
            + " · 🎯 优先级 " + str(card["priority_score"])
        )

    def action_line(card: dict[str, Any]) -> str:
        icon = ACTION_ICONS.get(card.get("recommended_action", ""), "➡️")
        return f"{icon} 建议：{card.get('recommended_action_zh') or card['recommended_action']}"

    new_cards = [
        c for c in cards
        if not c.get("is_historical") and (include_seen or not c.get("is_repeat"))
    ]
    repeated_cards = [c for c in cards if not c.get("is_historical") and c.get("is_repeat")]
    historical_cards = [c for c in cards if c.get("is_historical")]
    deep_reads = [c for c in new_cards if c["recommended_action"] in {"deep_read", "try_experiment"}]
    paper_deep_reads = [c for c in deep_reads if c["source_type"] != "industry"]
    industry_deep_reads = [c for c in deep_reads if c["source_type"] == "industry"]
    top_cards = [c for c in new_cards if c["source_type"] != "industry"][:report_limit]
    lines: list[str] = []
    lines.append(f"# 推荐算法研究日报 - {output_date}")
    lines.append("")
    lines.append("> 抓取结果保留英文原文；中文翻译由 skill 的翻译阶段补齐并置于原文之前。")
    lines.append(f"> 新增窗口：{window_label}；日报精选上限：{report_limit} 项。")
    if repeated_cards and not include_seen:
        lines.append(f"> 已自动去重：{len(repeated_cards)} 项此前已出现在日报中；可用 `--include-seen` 重新展示。")
    lines.append("")
    lines.append("## Executive Answer")
    lines.append("")
    if new_cards:
        lines.append(
            f"Found {len(new_cards)} new relevant recommendation-research items. "
            f"{len(deep_reads)} are deep-read or experiment candidates."
        )
        first = deep_reads[0] if deep_reads else new_cards[0]
        lines.append(
            f"优先阅读：[{first.get('title_zh') or first['title']}]({first['url']})；"
            f"原文标题：{first['title']}；原因：{first.get('deep_read_reason_zh') or first['deep_read_reason']}"
        )
    else:
        lines.append("No relevant items were fetched. Check source errors and widen the lookback window.")
    lines.append("")
    lines.append("## Source Coverage")
    lines.append("")
    for key in sorted(counts):
        lines.append(f"- {key}: {counts[key]}")
    if errors:
        lines.append("- source_errors:")
        for err in errors:
            lines.append(f"  - {err}")
    else:
        lines.append("- source_errors: none")
    lines.append("")
    lines.append("## 📊 今日主题聚类与趋势")
    lines.append("")
    topic_counts: dict[str, int] = {}
    for card in new_cards:
        for topic in card.get("matched_topics", []):
            topic_counts[topic] = topic_counts.get(topic, 0) + 1
    if topic_counts:
        for topic, count in sorted(topic_counts.items(), key=lambda pair: (-pair[1], pair[0]))[:6]:
            lines.append(f"- {TOPIC_LABELS_ZH.get(topic, topic)}：{count} 项")
        if topic_counts.get("ranking_learning_to_rank", 0) and topic_counts.get("systems_serving_infra", 0):
            lines.append("- 趋势：排序/重排正在与延迟、吞吐和服务架构联合优化。")
        if topic_counts.get("retrieval_candidate_generation", 0) and topic_counts.get("generative_llm_recommendation", 0):
            lines.append("- 趋势：召回层继续向生成式检索和大模型辅助候选生成扩展。")
        if topic_counts.get("sequential_user_modeling", 0):
            lines.append("- 趋势：用户建模重点从更长历史转向更有结构的序列和多兴趣状态。")
    else:
        lines.append("今日新增不足以形成稳定主题聚类。")
    lines.append("")
    lines.append("## 🔀 粗排与重排专题")
    lines.append("")
    reranking_cards = [
        card for card in new_cards
        if "coarse_reranking" in card.get("matched_topics", [])
    ]
    if reranking_cards:
        lines.append("本专题只收录明确命中粗排、重排或级联排序关键词的条目，便于单独跟踪效果-延迟权衡。")
        lines.append("")
        for card in sorted(reranking_cards, key=lambda c: c["priority_score"], reverse=True)[:8]:
            lines.append(
                f"- [{card.get('title_zh') or card['title']}]({card['url']}) — "
                f"{card['source_name']}；{card.get('recommended_action_zh') or card['recommended_action']}"
            )
    else:
        lines.append("本窗口暂无明确命中粗排/重排关键词的条目。")
    lines.append("")
    lines.append("## 🏢 大厂技术文章覆盖")
    lines.append("")
    industry_counts: dict[str, int] = {}
    for card in new_cards:
        if card["source_type"] == "industry":
            industry_counts[card["source_name"]] = industry_counts.get(card["source_name"], 0) + 1
    if industry_counts:
        for source_name, count in sorted(industry_counts.items(), key=lambda pair: (-pair[1], pair[0])):
            lines.append(f"- {source_name}: {count}")
        lines.append("")
        lines.append("### Article Index")
        lines.append("")
        for card in sorted(
            (c for c in cards if c["source_type"] == "industry"),
            key=lambda c: c["priority_score"],
            reverse=True,
        ):
            lines.append(
                f"- [{card.get('title_zh') or card['title']}]({card['url']}) — "
                f"{card['source_name']}；{action_line(card)}"
            )
            lines.append("")
    else:
        lines.append("- no relevant industry cards in this window")
    lines.append("")
    lines.append("## 🏛️ 历史精选")
    lines.append("")
    if historical_cards:
        for idx, card in enumerate(historical_cards[:4], 1):
            lines.append(f"{idx}. [{card.get('title_zh') or card['title']}]({card['url']})")
            lines.append(f"   - source: {card['source_name']} (historical pick)")
            lines.append(f"   - why: {card.get('deep_read_reason_zh') or card['deep_read_reason']}")
    else:
        lines.append("暂无历史精选。")
    lines.append("")
    lines.append("## 📚 论文深读队列")
    lines.append("")
    queue = paper_deep_reads[:8] or [c for c in top_cards if c["source_type"] != "industry"][:5]
    if not queue:
        lines.append("No deep-read candidates.")
    for idx, card in enumerate(queue, 1):
        lines.append(f"{idx}. [{card.get('title_zh') or card['title']}]({card['url']})")
        lines.append(f"   - original title: {card['title']}")
        lines.append(f"   - source: {card['source_name']} ({card['source_type']})")
        lines.append(f"   - {score_line(card)}")
        lines.append(f"   - {action_line(card)}")
        lines.append(f"   - why: {card.get('deep_read_reason_zh') or card['deep_read_reason']}")
    lines.append("")
    lines.append("## 📝 业界文章深读队列")
    lines.append("")
    if not industry_deep_reads:
        lines.append("本窗口没有达到深读阈值的业界文章；相关业界文章仍见上方“大厂技术文章覆盖”。")
    for idx, card in enumerate(industry_deep_reads[:8], 1):
        lines.append(f"{idx}. [{card.get('title_zh') or card['title']}]({card['url']})")
        lines.append(f"   - source: {card['source_name']}")
        lines.append(f"   - contribution: {card.get('core_contribution_zh') or card['core_contribution']}")
        lines.append(f"   - {score_line(card)}")
        lines.append(f"   - {action_line(card)}")
        lines.append(f"   - why: {card.get('deep_read_reason_zh') or card['deep_read_reason']}")
    lines.append("")
    lines.append("## 🗂️ 论文结构化卡片")
    lines.append("")
    for card in top_cards:
        lines.append(f"### {card.get('title_zh') or card['title']}")
        lines.append("")
        lines.append(f"- original title: {card['title']}")
        lines.append(f"- link: {card['url']}")
        lines.append(f"- contribution: {card.get('core_contribution_zh') or card['core_contribution']}")
        lines.append(f"- methods: {', '.join(card.get('methods_zh') or card['methods']) if card['methods'] else 'not explicit'}")
        lines.append(f"- limitations: {'; '.join(card.get('limitations_zh') or card['limitations']) if card.get('limitations') else 'not explicit'}")
        lines.append(f"- future directions: {'; '.join(card.get('future_directions_zh') or card['future_directions']) if card.get('future_directions') else 'not explicit'}")
        if card.get("related_reading"):
            related = card.get("related_reading_zh") or card["related_reading"]
            lines.append("- related reading: " + "; ".join(f"[{item['title']}]({item['url']})" for item in related))
        lines.append(
            "- datasets/benchmarks: "
            + (", ".join(card.get("datasets_or_benchmarks_zh") or card["datasets_or_benchmarks"]) if card["datasets_or_benchmarks"] else "not explicit")
        )
        lines.append(f"- matched topics: {', '.join(card['matched_topics']) if card['matched_topics'] else 'none'}")
        lines.append(f"- evidence: {'; '.join(card['evidence']) if card['evidence'] else 'limited feed metadata'}")
        if card["possible_experiments"]:
            experiment = card.get("possible_experiments_zh") or card["possible_experiments"]
            lines.append(f"- possible experiment: {experiment[0].get('experiment_zh') or experiment[0]['experiment']}")
        lines.append("")
    lines.append("## 💡 研究创意与小型实验")
    lines.append("")
    if not ideas:
        lines.append("No grounded small experiment ideas were generated.")
    for idx, idea in enumerate(ideas, 1):
        lines.append(f"{idx}. {idea.get('title_zh') or idea['title']}")
        lines.append(f"   - hypothesis: {idea.get('hypothesis_zh') or idea['hypothesis']}")
        lines.append(f"   - experiment: {idea.get('smallest_experiment_zh') or idea['smallest_experiment']}")
        lines.append(f"   - baseline: {idea.get('baseline_zh') or idea['baseline']}")
        lines.append(f"   - dataset/setup: {idea.get('dataset_or_setup_zh') or idea['dataset_or_setup']}")
        lines.append(f"   - metric: {idea.get('metric_zh') or idea['metric']}")
        lines.append(f"   - failure modes: {', '.join(idea.get('failure_modes_zh') or idea['failure_modes'])}")
    lines.append("")
    lines.append("## Action Plan")
    lines.append("")
    if queue:
        lines.append(f"- read today: {queue[0]['title']}")
    if ideas:
        lines.append(f"- implement this week: {ideas[0]['title']}")
    track = [c for c in new_cards if c["recommended_action"] == "track"]
    if track:
        lines.append(f"- track for later: {track[0]['title']}")
    if errors:
        lines.append("- coverage gaps to fix: inspect failed sources or add official proceedings/manual URLs.")
    else:
        lines.append("- coverage gaps to fix: add any conference proceedings or company post URLs not covered by feeds.")
    lines.append("")
    return "\n".join(lines)


def offline_items() -> list[SourceItem]:
    return [
        SourceItem(
            id="sample:retrieval-llm",
            source_type="arxiv",
            source_name="offline sample",
            title="Generative Retrieval Signals for Sequential Recommendation",
            authors=["Sample Author"],
            summary=(
                "This work proposes a lightweight generative recommendation module for "
                "sequential recommendation. It combines item retrieval with a small language "
                "model reranker and reports improvements on MovieLens and Amazon benchmarks."
            ),
            url="https://arxiv.org/abs/0000.00000",
            published=today_string(),
            categories=["cs.IR"],
        ),
        SourceItem(
            id="sample:bandit-eval",
            source_type="conference",
            source_name="offline sample",
            title="Counterfactual Evaluation for Long-Term Recommendation",
            authors=["Sample Researcher"],
            summary=(
                "We introduce an off-policy evaluation method for long-term value in "
                "recommender systems. Experiments show reduced bias compared with IPS on "
                "synthetic logged bandit feedback."
            ),
            url="https://openreview.net/forum?id=sample",
            published=today_string(),
            categories=["ICLR.cc/2026/Conference"],
        ),
        SourceItem(
            id="sample:serving",
            source_type="industry",
            source_name="offline sample",
            title="Reducing Recommendation Ranking Latency in Production",
            authors=[],
            summary=(
                "An engineering post describes production recommender serving changes, "
                "including feature cache redesign and distillation for a ranking model. "
                "An online experiment reduced p95 latency while maintaining CTR."
            ),
            url="https://example.com/recsys-serving",
            published=today_string(),
            categories=[],
        ),
    ]


def historical_items(catalog: dict[str, Any]) -> list[SourceItem]:
    items: list[SourceItem] = []
    for raw in catalog.get("historical_picks", []):
        items.append(
            SourceItem(
                id=raw["id"],
                source_type=raw.get("source_type", "historical_paper"),
                source_name=raw["source_name"],
                title=raw["title"],
                authors=raw.get("authors", []),
                summary=raw["summary"],
                url=raw["url"],
                published=raw.get("published"),
                categories=raw.get("categories", []),
            )
        )
    return items


def collect_items(
    args: argparse.Namespace,
    catalog: dict[str, Any],
    window_start: datetime,
    window_end: datetime,
) -> tuple[list[SourceItem], list[str], dict[str, int]]:
    if args.offline_sample:
        items = offline_items()
        counts = {"offline_sample": len(items)}
        if args.include_history:
            history = historical_items(catalog)
            items.extend(history)
            counts["historical"] = len(history)
        return items, [], counts

    sources = set(args.sources.split(","))
    all_items: list[SourceItem] = []
    errors: list[str] = []
    counts: dict[str, int] = {}

    if "arxiv" in sources:
        items, errs = fetch_arxiv(catalog, args.max_results, window_start, window_end)
        all_items.extend(items)
        errors.extend(errs)
        counts["arxiv"] = len(items)
        time.sleep(args.polite_delay)
    if "openreview" in sources:
        items, errs = fetch_openreview(catalog, args.max_results, window_start, window_end)
        all_items.extend(items)
        errors.extend(errs)
        counts["openreview"] = len(items)
        time.sleep(args.polite_delay)
    if "rss" in sources:
        items, errs = fetch_rss(catalog, args.max_results, window_start, window_end)
        all_items.extend(items)
        errors.extend(errs)
        counts["rss"] = len(items)
        time.sleep(args.polite_delay)
    if "manual" in sources:
        items, errs = fetch_manual_urls(catalog, args.lookback_days)
        all_items.extend(items)
        errors.extend(errs)
        counts["manual"] = len(items)

    if args.include_history:
        items = historical_items(catalog)
        all_items.extend(items)
        counts["historical"] = len(items)

    return dedupe_items(all_items), errors, counts


def write_outputs(
    output_dir: Path,
    cards: list[dict[str, Any]],
    ideas: list[dict[str, Any]],
    report: str,
    output_date: str,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    cards_path = output_dir / f"cards-{output_date}.json"
    ideas_path = output_dir / f"ideas-{output_date}.json"
    report_path = output_dir / f"daily-{output_date}.md"
    cards_path.write_text(json.dumps(cards, ensure_ascii=False, indent=2), encoding="utf-8")
    ideas_path.write_text(json.dumps(ideas, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(report, encoding="utf-8")
    return {
        "cards": str(cards_path),
        "ideas": str(ideas_path),
        "report": str(report_path),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch RecSys research sources and generate paper cards plus a daily report.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """
            Examples:
              python3 scripts/fetch_recsys_research.py --offline-sample
              python3 scripts/fetch_recsys_research.py --lookback-days 2 --sources arxiv,rss
            """
        ),
    )
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--lookback-days", type=int, default=2)
    parser.add_argument(
        "--window-mode",
        choices=("workday", "calendar"),
        default="workday",
        help="workday uses the previous workday (and weekend on Monday); calendar uses lookback-days.",
    )
    parser.add_argument("--as-of", help="Local Asia/Shanghai ISO datetime for deterministic window tests.")
    parser.add_argument("--max-results", type=int, default=40)
    parser.add_argument("--report-limit", type=int, default=8)
    parser.add_argument("--state-file", type=Path, help="Persistent cross-run deduplication state JSON path.")
    parser.add_argument("--sources", default="arxiv,openreview,rss,manual")
    parser.add_argument("--polite-delay", type=float, default=1.0)
    parser.add_argument("--offline-sample", action="store_true")
    parser.add_argument("--no-history", dest="include_history", action="store_false")
    parser.add_argument("--include-seen", action="store_true", help="Include items already reported in the current-window sections.")
    parser.set_defaults(include_history=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    catalog = load_catalog(args.catalog)
    window_start, window_end, window_label = compute_window(args.window_mode, args.lookback_days, args.as_of)
    items, errors, counts = collect_items(args, catalog, window_start, window_end)
    cards = [score_item(item, catalog) for item in items]
    cards = [c for c in cards if c["recommended_action"] != "ignore"]
    new_cards = sorted(
        (c for c in cards if not c.get("is_historical")),
        key=lambda c: c["priority_score"],
        reverse=True,
    )[: args.max_results]
    historical_cards = sorted(
        (c for c in cards if c.get("is_historical")),
        key=lambda c: c["priority_score"],
        reverse=True,
    )
    cards = new_cards + historical_cards
    state_path = args.state_file or args.output_dir / "radar-state.json"
    state = load_state(state_path)
    apply_state(cards, state)
    idea_cards = [
        c for c in cards
        if not c.get("is_historical") and (args.include_seen or not c.get("is_repeat"))
    ]
    ideas = build_ideas(idea_cards)
    output_date = window_end.astimezone(LOCAL_TZ).date().isoformat()
    report = render_report(cards, ideas, errors, counts, output_date, window_label, args.report_limit, args.include_seen)
    paths = write_outputs(args.output_dir, cards, ideas, report, output_date)
    update_state(cards, state, now_iso())
    save_state(state_path, state)
    paths["state"] = str(state_path)

    print(json.dumps({"counts": counts, "cards": len(cards), "ideas": len(ideas), "paths": paths}, ensure_ascii=False, indent=2))
    if errors:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
