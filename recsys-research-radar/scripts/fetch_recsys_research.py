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
import os
import re
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from translation_pass import apply_translation_payload, missing_translation_fields


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULT_CATALOG = SKILL_DIR / "references" / "source_catalog.json"
DEFAULT_OUTPUT_DIR = Path("/Users/wangbaojiang/Nutstore Files/我的坚果云/日常/推荐论文日报")

ARXIV_API_MIRRORS = (
    "https://export.arxiv.org/api/query",
    "https://arxiv.org/api/query",
)
OPENALEX_API = "https://api.openalex.org/works"
SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1/paper/search"
OPENREVIEW_NOTES_API = "https://api2.openreview.net/notes"
USER_AGENT = "RecSysResearchRadar/0.1 (local Codex skill; mailto:research@localhost)"
LOCAL_TZ = ZoneInfo("Asia/Shanghai")
TOPIC_LABELS_ZH = {
    "retrieval_candidate_generation": "召回与候选生成",
    "search_retrieval": "搜索与信息检索",
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
ACTION_LABELS_ZH = {
    "deep_read": "深读",
    "try_experiment": "尝试小实验",
    "summarize": "快速总结",
    "track": "持续跟踪",
    "ignore": "忽略",
}
METHOD_LABELS_ZH = {
    "a/b test": "线上 A/B 实验",
    "ads ranking": "广告排序",
    "attention": "注意力机制",
    "bandit": "多臂老虎机/探索策略",
    "behavior sequence": "行为序列建模",
    "bm25": "BM25 词法检索",
    "calibration": "校准",
    "causal": "因果方法",
    "click-through rate": "点击率预测（CTR）",
    "contrastive learning": "对比学习",
    "counterfactual": "反事实学习/评估",
    "ctr": "点击率预测（CTR）",
    "ctr prediction": "点击率预测",
    "distillation": "知识蒸馏",
    "dual encoder": "双编码器",
    "exploration": "探索",
    "gnn": "图神经网络（GNN）",
    "graph neural network": "图神经网络（GNN）",
    "large language model": "大语言模型（LLM）",
    "latency": "延迟优化",
    "learning to rank": "学习排序",
    "llm": "大语言模型（LLM）",
    "llm-native recommendation": "LLM 原生推荐",
    "matrix factorization": "矩阵分解",
    "multi-task": "多任务学习",
    "real-time": "实时处理",
    "reinforcement learning": "强化学习",
    "reranking": "重排",
    "retrieval": "召回/检索",
    "ranking": "排序",
    "ranker": "排序器",
    "serving": "在线服务",
    "sequential recommendation": "序列推荐",
    "transformer": "Transformer 序列模型",
    "two-tower": "双塔召回",
    "vector search": "向量检索",
    "video recommendation": "视频推荐",
}
DATASET_LABELS_ZH = {
    "amazon": "Amazon 评论数据",
    "alibaba": "阿里巴巴数据",
    "avazu": "Avazu 广告点击数据",
    "criteo": "Criteo 点击率数据",
    "gowalla": "Gowalla 轨迹数据",
    "kuairec": "KuaiRec 推荐数据",
    "kuairand": "KuaiRand 推荐数据",
    "lastfm": "Last.fm 音乐推荐数据",
    "mind": "MIND 新闻推荐数据",
    "ml-1m": "MovieLens-1M",
    "ml-20m": "MovieLens-20M",
    "movielens": "MovieLens 数据",
    "steam": "Steam 物品推荐数据",
    "taobao": "淘宝数据",
    "yelp": "Yelp 商户数据",
}
RELATED_TITLE_LABELS_ZH = {
    "Deep Neural Networks for YouTube Recommendations": "用于 YouTube 推荐的深度神经网络",
    "DeepCT: Deep Reinforcement Learning for Contextual Text Representation": "DeepCT：用于上下文文本表示的深度强化学习",
    "Deep Interest Network for Click-Through Rate Prediction": "用于点击率预测的深度兴趣网络",
    "Deep Interest Evolution Network for Click-Through Rate Prediction": "用于点击率预测的深度兴趣演化网络",
    "GenRec: Towards LLM-Native Recommendation at Netflix": "GenRec：迈向 Netflix 的 LLM 原生推荐",
}
RELATED_READING = {
    "retrieval_candidate_generation": [
        {"title": "Deep Neural Networks for YouTube Recommendations", "url": "https://research.google/pubs/deep-neural-networks-for-youtube-recommendations/", "relation": "经典的候选生成与排序两阶段工业架构"},
    ],
    "search_retrieval": [
        {"title": "DeepCT: Deep Reinforcement Learning for Contextual Text Representation", "url": "https://arxiv.org/abs/1808.09600", "relation": "把查询/文档表示学习引入信息检索，可迁移到推荐召回与重排"},
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

ADJACENT_TRANSFER_ANCHORS = (
    "information retrieval",
    "search ranking",
    "query understanding",
    "query rewriting",
    "semantic search",
    "dense retrieval",
    "ad ranking",
    "ads ranking",
    "ctr prediction",
    "cvr prediction",
    "multi-objective ranking",
    "llm recommender",
    "large language model recommendation",
    "generative recommendation",
    "agentic recommendation",
    "retrieval augmented generation",
    "信息检索",
    "搜索排序",
    "查询理解",
    "广告排序",
    "点击率预测",
    "转化率预测",
    "大模型推荐",
    "生成式推荐",
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
    "search_retrieval": {
        "experiment": "Compare a lexical BM25 retriever, dense retriever, and a lightweight reranker on a small query-item relevance set.",
        "baseline": "BM25 or TF-IDF retrieval",
        "metric": "Recall@50, NDCG@10, query latency, and performance on tail queries",
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
    summary_zh: str | None = None
    contribution_zh: str | None = None


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


def fetch_bytes(
    url: str,
    timeout: float = 30.0,
    headers: dict[str, str] | None = None,
) -> bytes:
    request_headers = {"User-Agent": USER_AGENT}
    if headers:
        request_headers.update(headers)
    req = urllib.request.Request(url, headers=request_headers)
    opener = urllib.request.build_opener(HTTP308RedirectHandler)
    with opener.open(req, timeout=timeout) as resp:
        return resp.read()


def fetch_curl_bytes(
    url: str,
    timeout: float = 90.0,
    attempts: int = 3,
    headers: dict[str, str] | None = None,
) -> bytes:
    """Fetch public APIs through curl because urllib can stall in local proxy/DNS setups."""
    last_error = ""
    retry_max_time = max(5, min(int(timeout), 20))
    for attempt in range(1, attempts + 1):
        try:
            result = subprocess.run(
                [
                    "curl",
                    "-fsSL",
                    "--retry",
                    "1",
                    "--retry-delay",
                    "1",
                    "--retry-all-errors",
                    "--connect-timeout",
                    str(min(10, int(timeout))),
                    "--max-time",
                    str(int(timeout)),
                    "--retry-max-time",
                    str(retry_max_time),
                    "-A",
                    USER_AGENT,
                ]
                + [arg for key, value in (headers or {}).items() for arg in ("-H", f"{key}: {value}")]
                + [url],
                check=True,
                capture_output=True,
                timeout=timeout + 10,
            )
            if result.stdout:
                return result.stdout
            last_error = "empty response"
        except (OSError, subprocess.SubprocessError) as exc:
            stderr = getattr(exc, "stderr", b"")
            detail = stderr.decode("utf-8", errors="ignore").strip() if isinstance(stderr, bytes) else str(stderr)
            last_error = f"{exc}; {detail}" if detail else str(exc)
        if attempt < attempts:
            time.sleep(2 ** (attempt - 1))
    raise urllib.error.URLError(f"curl failed after {attempts} attempts: {last_error}")


def fetch_arxiv_bytes(url: str, timeout: float = 90.0, attempts: int = 3) -> bytes:
    return fetch_curl_bytes(url, timeout=timeout, attempts=attempts)


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


def build_arxiv_queries(categories: list[str], keywords: list[str], chunk_size: int = 8) -> list[str]:
    """Split the catalog into short queries so one oversized request cannot sink the run."""
    if not keywords:
        return [build_arxiv_query(categories, keywords)]
    return [
        build_arxiv_query(categories, keywords[index:index + chunk_size])
        for index in range(0, len(keywords), chunk_size)
    ]


def fetch_arxiv(
    catalog: dict[str, Any],
    max_results: int,
    window_start: datetime,
    window_end: datetime,
    cache_path: Path | None = None,
) -> tuple[list[SourceItem], list[str]]:
    cfg = catalog.get("arxiv", {})
    categories = cfg.get("categories", [])
    keywords = cfg.get("keywords", [])
    errors: list[str] = []
    has_cache = bool(cache_path and cache_path.exists())
    items_by_id: dict[str, SourceItem] = {}
    query_failures = 0
    for query in build_arxiv_queries(categories, keywords):
        params = urllib.parse.urlencode(
            {
                "search_query": query,
                "start": 0,
                "max_results": min(max_results, 50),
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }
        )
        content = None
        for mirror_index, api in enumerate(ARXIV_API_MIRRORS):
            url = f"{api}?{params}"
            try:
                content = fetch_arxiv_bytes(
                    url,
                    timeout=15.0 if has_cache else 30.0,
                    attempts=2,
                )
                if mirror_index:
                    errors.append(f"arXiv fallback used: {api}")
                break
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                query_failures += 1
                errors.append(f"warning: arXiv endpoint failed ({api}): {exc}")
        if content is None:
            continue
        try:
            for item in parse_arxiv_feed(content, window_start, window_end):
                items_by_id[item.id] = item
        except ET.ParseError as exc:
            errors.append(f"warning: arXiv response parse failed: {exc}")

    if items_by_id:
        items = list(items_by_id.values())[:max_results]
        save_arxiv_cache(cache_path, items)
        return items, errors

    if query_failures:
        fallback_items, fallback_errors = fetch_openalex_arxiv(catalog, max_results, window_start, window_end)
        if fallback_items:
            errors.append("arXiv fallback used: OpenAlex index of arXiv-linked works")
            save_arxiv_cache(cache_path, fallback_items)
            return fallback_items, errors + fallback_errors
        errors.extend(f"warning: {error}" for error in fallback_errors)

    if os.environ.get("SEMANTIC_SCHOLAR_API_KEY"):
        fallback_items, fallback_errors = fetch_semantic_scholar(catalog, max_results, window_start, window_end)
        if fallback_items:
            errors.append("arXiv fallback used: Semantic Scholar arXiv index")
            save_arxiv_cache(cache_path, fallback_items)
            return fallback_items, errors + fallback_errors
        errors.extend(f"warning: {error}" for error in fallback_errors)
    else:
        errors.append("warning: Semantic Scholar fallback skipped: set SEMANTIC_SCHOLAR_API_KEY for this optional source")

    cached_items = load_arxiv_cache(cache_path, max_results)
    if cached_items:
        errors.append("arXiv fallback used: most recent local metadata cache")
        return cached_items, errors
    errors.append("error: arXiv unavailable after mirror, OpenAlex, Semantic Scholar, and cache fallbacks")
    return [], errors


def parse_arxiv_feed(
    content: bytes,
    window_start: datetime,
    window_end: datetime,
) -> list[SourceItem]:
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
    return items


def save_arxiv_cache(path: Path | None, items: list[SourceItem]) -> None:
    if path is None or not items:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(item) for item in items], ensure_ascii=False, indent=2), encoding="utf-8")


def load_arxiv_cache(path: Path | None, limit: int) -> list[SourceItem]:
    if path is None or not path.exists():
        return []
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    cached: list[SourceItem] = []
    for record in records[:limit]:
        if not record.get("id") or not record.get("title"):
            continue
        record["source_name"] = "arXiv (本地缓存兜底)"
        cached.append(SourceItem(**record))
    return cached


def reconstruct_openalex_abstract(inverted_index: dict[str, list[int]] | None) -> str:
    if not inverted_index:
        return ""
    words = [
        (position, word)
        for word, positions in inverted_index.items()
        for position in positions
    ]
    return " ".join(word for _, word in sorted(words))


def fetch_openalex_arxiv(
    catalog: dict[str, Any],
    max_results: int,
    window_start: datetime,
    window_end: datetime,
) -> tuple[list[SourceItem], list[str]]:
    """Use OpenAlex as a second metadata index when arXiv's API is unreachable."""
    queries = [
        "recommender system",
        "recommendation ranking retrieval",
        "generative recommendation",
    ]
    items: dict[str, SourceItem] = {}
    errors: list[str] = []
    date_filter = (
        f"from_publication_date:{window_start.date().isoformat()},"
        f"to_publication_date:{window_end.date().isoformat()}"
    )
    for query in queries:
        params = urllib.parse.urlencode(
            {
                "search": query,
                "filter": date_filter,
                "per-page": min(25, max_results),
            }
        )
        try:
            payload = json.loads(fetch_curl_bytes(f"{OPENALEX_API}?{params}", timeout=30, attempts=2))
        except (json.JSONDecodeError, urllib.error.URLError, TimeoutError, OSError) as exc:
            errors.append(f"OpenAlex arXiv fallback failed for {query}: {exc}")
            continue
        for work in payload.get("results", []):
            locations = [work.get("primary_location"), work.get("best_oa_location")]
            arxiv_url = ""
            for location in locations:
                landing = (location or {}).get("landing_page_url") or ""
                match = re.search(r"arxiv\.org/(?:abs|pdf)/([0-9.]+)", landing)
                if match:
                    arxiv_url = f"https://arxiv.org/abs/{match.group(1)}"
                    break
            if not arxiv_url:
                continue
            arxiv_id = arxiv_url.rsplit("/", 1)[-1]
            authors = [
                (author.get("author") or {}).get("display_name", "")
                for author in work.get("authorships", [])
            ]
            items[f"arxiv:{arxiv_id}"] = SourceItem(
                id=f"arxiv:{arxiv_id}",
                source_type="arxiv",
                source_name="arXiv (OpenAlex fallback)",
                title=normalize_space(work.get("title", "")),
                authors=[author for author in authors if author],
                summary=reconstruct_openalex_abstract(work.get("abstract_inverted_index")),
                url=arxiv_url,
                published=work.get("publication_date"),
                categories=["OpenAlex index"],
            )
            if len(items) >= max_results:
                break
        if len(items) >= max_results:
            break
    return list(items.values())[:max_results], errors


def fetch_semantic_scholar(
    catalog: dict[str, Any],
    max_results: int,
    window_start: datetime,
    window_end: datetime,
) -> tuple[list[SourceItem], list[str]]:
    """Use Semantic Scholar's arXiv-indexed metadata as a scholarly fallback."""
    queries = [
        "recommender system",
        "recommendation ranking retrieval",
        "generative recommendation",
    ]
    items: dict[str, SourceItem] = {}
    errors: list[str] = []
    for query in queries:
        params = urllib.parse.urlencode(
            {
                "query": query,
                "limit": min(15, max_results),
                "fields": "title,abstract,authors,publicationDate,externalIds",
            }
        )
        try:
            payload = json.loads(fetch_curl_bytes(f"{SEMANTIC_SCHOLAR_API}?{params}", timeout=45, attempts=2))
        except (json.JSONDecodeError, urllib.error.URLError, TimeoutError, OSError) as exc:
            errors.append(f"Semantic Scholar fallback failed for {query}: {exc}")
            continue
        for paper in payload.get("data", []):
            external_ids = paper.get("externalIds") or {}
            arxiv_id = external_ids.get("ArXiv")
            published = paper.get("publicationDate")
            if not arxiv_id or not within_window(published, window_start, window_end):
                continue
            item_id = f"arxiv:{arxiv_id}"
            items[item_id] = SourceItem(
                id=item_id,
                source_type="arxiv",
                source_name="arXiv (Semantic Scholar fallback)",
                title=normalize_space(paper.get("title", "")),
                authors=[a.get("name", "") for a in paper.get("authors", []) if a.get("name")],
                summary=normalize_space(paper.get("abstract", "")),
                url=f"https://arxiv.org/abs/{arxiv_id}",
                published=published,
                categories=["cs.IR"],
            )
            if len(items) >= max_results:
                break
        if len(items) >= max_results:
            break
        time.sleep(1)
    return list(items.values()), errors


def fetch_openreview(catalog: dict[str, Any], max_results: int, window_start: datetime, window_end: datetime) -> tuple[list[SourceItem], list[str]]:
    access_token = os.environ.get("OPENREVIEW_ACCESS_TOKEN") or os.environ.get("OPENREVIEW_TOKEN")
    if not access_token:
        return [], [
            "warning: OpenReview skipped: API2 requires OPENREVIEW_ACCESS_TOKEN; "
            "use the official conference portal when no credential is configured"
        ]
    venue_ids = catalog.get("openreview", {}).get("venue_ids", [])
    items: list[SourceItem] = []
    errors: list[str] = []
    per_venue = max(1, max_results // max(1, len(venue_ids)))
    headers = {"Cookie": f"openreview.accessToken={access_token}"}
    for venue_id in venue_ids:
        params = urllib.parse.urlencode(
            {"content.venue_id": venue_id, "limit": per_venue, "sort": "tmdate:desc"}
        )
        url = f"{OPENREVIEW_NOTES_API}?{params}"
        try:
            payload = json.loads(fetch_bytes(url, headers=headers).decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                errors.append(f"warning: OpenReview API2 authorization failed for {venue_id}: HTTP {exc.code}")
            else:
                errors.append(f"warning: OpenReview API2 fetch failed for {venue_id}: HTTP {exc.code}")
            continue
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            errors.append(f"warning: OpenReview API2 fetch failed for {venue_id}: {exc}")
            continue
        for note in payload.get("notes", []):
            content = note.get("content", {})
            title = normalize_space(text_of(content.get("title")))
            abstract = normalize_space(text_of(content.get("abstract")))
            raw_authors = content.get("authors")
            if isinstance(raw_authors, dict) and "value" in raw_authors:
                raw_authors = raw_authors["value"]
            if isinstance(raw_authors, list):
                author_list = [text_of(author) for author in raw_authors if text_of(author)]
            else:
                author_list = [author.strip() for author in text_of(raw_authors).split(",") if author.strip()]
            cdate = note.get("pdate") or note.get("cdate") or note.get("mdate")
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
            if not any(
                contains_keyword(haystack, k)
                for k in RECSYS_KEYWORDS + ADJACENT_TRANSFER_ANCHORS
            ):
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


def extract_meta_description(page: str) -> str:
    for tag in re.findall(r"<meta\b[^>]*>", page, flags=re.I):
        attributes = {
            key.lower(): html.unescape(value)
            for key, value in re.findall(r"([:\w-]+)\s*=\s*[\"'](.*?)[\"']", tag, flags=re.I | re.S)
        }
        name = (attributes.get("name") or attributes.get("property") or "").lower()
        if name in {"description", "og:description", "twitter:description"}:
            return normalize_space(attributes.get("content", ""))
    return ""


def extract_page_text(page: str) -> str:
    cleaned = re.sub(r"<(script|style|noscript|svg)\b.*?</\1>", " ", page, flags=re.I | re.S)
    return normalize_space(re.sub(r"<[^>]+>", " ", cleaned))


def fetch_manual_urls(catalog: dict[str, Any], lookback_days: int) -> tuple[list[SourceItem], list[str]]:
    items: list[SourceItem] = []
    errors: list[str] = []
    for raw in catalog.get("manual_urls", []):
        url = raw.get("url") if isinstance(raw, dict) else str(raw)
        name = raw.get("name", "Manual URL") if isinstance(raw, dict) else "Manual URL"
        source_type = raw.get("source_type", "manual") if isinstance(raw, dict) else "manual"
        configured_title = normalize_space(raw.get("title", "")) if isinstance(raw, dict) else ""
        configured_summary = normalize_space(raw.get("summary", "")) if isinstance(raw, dict) else ""
        configured_summary_zh = normalize_space(raw.get("summary_zh", "")) if isinstance(raw, dict) else ""
        configured_contribution_zh = normalize_space(raw.get("contribution_zh", "")) if isinstance(raw, dict) else ""
        try:
            page = fetch_bytes(url).decode("utf-8", errors="ignore")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            errors.append(f"Manual URL fetch failed for {url}: {exc}")
            continue
        title_match = re.search(r"<title[^>]*>(.*?)</title>", page, flags=re.I | re.S)
        title = configured_title or (normalize_space(title_match.group(1)) if title_match else url)
        text = extract_page_text(page)
        summary = configured_summary or extract_meta_description(page) or text[:1200]
        relevance_text = f"{title}\n{summary}\n{configured_summary_zh}\n{text}"
        if not any(contains_keyword(relevance_text.lower(), k) for k in RECSYS_KEYWORDS):
            continue
        items.append(
            SourceItem(
                id=make_id("manual", url),
                source_type=source_type,
                source_name=name,
                title=title,
                authors=[],
                summary=summary,
                url=url,
                published=raw.get("published") if isinstance(raw, dict) else None,
                categories=raw.get("categories", []) if isinstance(raw, dict) else [],
                summary_zh=configured_summary_zh or None,
                contribution_zh=configured_contribution_zh or None,
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


def translate_experiment_template(experiment: dict[str, str]) -> dict[str, str]:
    experiment_text = experiment.get("experiment", "")
    translations = {
        "Compare a two-tower retrieval baseline against the proposed retrieval signal on a small implicit-feedback matrix.": "在小型隐式反馈矩阵上，对比双塔召回基线与论文提出的召回信号。",
        "Compare a lexical BM25 retriever, dense retriever, and a lightweight reranker on a small query-item relevance set.": "在小型查询-物品相关性集合上，对比 BM25 词法检索、稠密检索和轻量级重排器。",
        "Train a tiny reranker with and without the proposed feature/objective on a public click dataset subset.": "在公开点击数据子集上，分别训练加入和不加入该特征/目标的小型重排模型。",
        "Compare a lightweight coarse ranker plus reranker cascade against a single-stage ranker on a small click dataset.": "在小型点击数据集上，对比轻量粗排加重排的级联方案与单阶段排序模型。",
        "Test whether the sequence modeling change improves next-item prediction on MovieLens or synthetic sessions.": "在 MovieLens 或合成会话上，测试序列建模改动是否提升下一物品预测。",
        "Evaluate a small LLM/RAG recommendation prompt against a non-generative retrieval/ranking pipeline on sampled items.": "在采样物品上，对比小型 LLM/RAG 推荐提示与非生成式召回-排序链路。",
        "Add lightweight image/text embeddings to an item retrieval baseline and measure lift on sparse users.": "在物品召回基线上加入轻量图像/文本 Embedding，测量稀疏用户上的收益。",
        "Compare graph propagation depth against matrix factorization on a small user-item graph.": "在小型用户-物品图上，对比不同图传播深度与矩阵分解。",
        "Run an offline policy evaluation toy study for the proposed debiasing or exploration idea.": "针对论文提出的去偏或探索方法，运行一个离线策略评估玩具实验。",
        "Measure the proposed metric or debiasing trick on a small recommendation benchmark with popularity slices.": "在带有流行度分层的小型推荐基准上，测量该指标或去偏技巧的效果。",
        "Prototype the serving optimization on a tiny retrieval/ranking service and measure speed-quality tradeoff.": "在小型召回/排序服务中实现该服务优化原型，测量速度与质量的权衡。",
        "Simulate the ranking or auction change on synthetic marketplace logs with constrained diversity.": "在带多样性约束的合成市场日志上，模拟排序或竞价机制改动。",
    }
    baseline_translations = {
        "matrix factorization or BM25-style popularity retrieval": "矩阵分解或 BM25 风格的流行度召回",
        "BM25 or TF-IDF retrieval": "BM25 或 TF-IDF 召回",
        "logistic regression or LambdaMART-style ranking baseline": "逻辑回归或 LambdaMART 风格排序基线",
        "single-stage logistic regression or LambdaMART ranker": "单阶段逻辑回归或 LambdaMART 排序器",
        "popularity, item-kNN, or SASRec-lite": "流行度、item-kNN 或 SASRec-lite",
        "retrieval plus heuristic reranking": "召回加启发式重排",
        "ID-only collaborative filtering": "仅使用 ID 的协同过滤",
        "BPR-MF or LightGCN with one fixed depth": "BPR-MF 或固定传播深度的 LightGCN",
        "IPS/SNIPS or epsilon-greedy simulator": "IPS/SNIPS 或 epsilon-greedy 模拟器",
        "standard sampled offline evaluation": "标准采样离线评估",
        "unoptimized batch inference or exact search": "未优化的批量推理或精确搜索",
        "CTR-only ranking or second-price auction toy model": "仅按 CTR 排序或二价竞价玩具模型",
    }
    metric_translations = {
        "Recall@50, NDCG@50, and embedding build/query time": "Recall@50、NDCG@50，以及 Embedding 构建/查询耗时",
        "Recall@50, NDCG@10, query latency, and performance on tail queries": "Recall@50、NDCG@10、查询延迟，以及长尾查询表现",
        "NDCG@10, AUC, calibration error, and inference latency": "NDCG@10、AUC、校准误差和推理延迟",
        "Recall@K, NDCG@10, p95 latency, and candidate reduction ratio": "Recall@K、NDCG@10、p95 延迟和候选集压缩比例",
        "HitRate@10, NDCG@10, and cold-start breakdown": "HitRate@10、NDCG@10，以及冷启动分层结果",
        "NDCG@10, coverage, refusal/error rate, and cost per query": "NDCG@10、覆盖率、拒答/错误率和单查询成本",
        "Recall@20 and performance by user-history length": "Recall@20，以及按用户历史长度分层的表现",
        "NDCG@20, training time, and popularity bias": "NDCG@20、训练耗时和流行度偏差",
        "estimated reward bias, variance, and regret in simulation": "模拟中的估计奖励偏差、方差和遗憾值",
        "NDCG@10, catalog coverage, Gini exposure, and slice lift": "NDCG@10、目录覆盖率、Gini 曝光指标和分层提升",
        "p95 latency, throughput, Recall@K, and memory footprint": "p95 延迟、吞吐量、Recall@K 和内存占用",
        "utility, revenue proxy, exposure fairness, and conversion proxy": "效用、收入代理指标、曝光公平性和转化代理指标",
    }
    return {
        "experiment_zh": translations.get(experiment_text, "小型实验方案待补充"),
        "baseline_zh": baseline_translations.get(experiment.get("baseline", ""), "基线方案待补充"),
        "metric_zh": metric_translations.get(experiment.get("metric", ""), "评估指标待补充"),
    }


def translate_related_reading(items: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "title_zh": RELATED_TITLE_LABELS_ZH.get(item.get("title", ""), "相关方法与背景阅读"),
            "relation_zh": item.get("relation", "相关方法与背景"),
            "url": item.get("url", ""),
        }
        for item in items
    ]


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
    has_adjacent_transfer_signal = any(
        contains_keyword(text, anchor) for anchor in ADJACENT_TRANSFER_ANCHORS
    )

    relevance = 0.0
    if matched_topics:
        relevance = 0.8 + topic_weight * 0.55
    if item.source_type == "arxiv" and "cs.ir" in categories:
        relevance += 0.4
    if item.source_type in {"conference", "industry"} and matched_topics:
        relevance += 0.3
    if item.source_type == "arxiv" and not (has_recsys_anchor or has_adjacent_transfer_signal):
        relevance -= 1.7
    if has_adjacent_transfer_signal and not has_recsys_anchor:
        relevance -= 0.5
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

    methods = extract_methods(text, matched_keywords)
    datasets = extract_datasets(text)
    related_reading = build_related_reading(matched_topics)

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
        "abstract_or_excerpt_zh": item.summary_zh or "",
        "core_contribution": extract_contribution(item.title, item.summary),
        "core_contribution_zh": item.contribution_zh or "",
        "methods": methods,
        "methods_zh": [METHOD_LABELS_ZH.get(method.lower(), "方法说明待补充") for method in methods],
        "claims": extract_claims(item.summary),
        "claims_zh": [],
        "limitations": extract_limitations(item.summary),
        "limitations_zh": [],
        "future_directions": extract_future_directions(item.summary),
        "future_directions_zh": [],
        "related_reading": related_reading,
        "related_reading_zh": translate_related_reading(related_reading),
        "datasets_or_benchmarks": datasets,
        "datasets_or_benchmarks_zh": [DATASET_LABELS_ZH.get(dataset.lower(), "数据集说明待补充") for dataset in datasets],
        "matched_topics": matched_topics,
        "relevance_score": relevance,
        "novelty_score": novelty,
        "implementation_difficulty": difficulty,
        "experimentability_score": experimentability,
        "priority_score": round(priority, 3),
        "recommended_action": action,
        "recommended_action_zh": ACTION_LABELS_ZH.get(action, "行动建议待补充"),
        "deep_read_reason": build_deep_read_reason(relevance, novelty, difficulty, matched_topics),
        "deep_read_reason_zh": build_deep_read_reason_zh(relevance, novelty, difficulty, matched_topics),
        "possible_experiments": experiments,
        "possible_experiments_zh": [translate_experiment_template(experiment) for experiment in experiments],
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


def build_deep_read_reason_zh(
    relevance: float, novelty: float, difficulty: float, matched_topics: list[str]
) -> str:
    topics = [TOPIC_LABELS_ZH.get(topic, topic) for topic in matched_topics[:3]]
    reasons = [f"与{ '、'.join(topics) }相关" if topics else "与推荐算法的直接关联仍需核验"]
    if relevance >= 3.5:
        reasons.append("相关性较高")
    if novelty >= 3.0:
        reasons.append("包含明确的新颖性线索")
    if difficulty <= 3.0:
        reasons.append("适合先做小型实验")
    return "；".join(reasons) + f"（实现难度 {difficulty}/5）"


def dedupe_items(items: list[SourceItem]) -> list[SourceItem]:
    seen: dict[str, SourceItem] = {}
    out: list[SourceItem] = []
    for item in items:
        key = re.sub(r"\W+", "", item.title.lower())[:160] or item.url
        existing = seen.get(key)
        if existing:
            if len(item.summary) > len(existing.summary):
                existing.summary = item.summary
            if item.summary_zh:
                existing.summary_zh = item.summary_zh
            if item.contribution_zh:
                existing.contribution_zh = item.contribution_zh
            continue
        seen[key] = item
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
        template_zh = translate_experiment_template(template)
        dataset_or_setup = choose_dataset(card)
        ideas.append(
            {
                "title": "Mini test: " + shorten(title, 80),
                "title_zh": "小实验：对应原文论文/文章",
                "source_item_ids": [card["id"]],
                "hypothesis": (
                    "The method or signal described in the source item improves at least one "
                    "offline recommendation metric over a simple baseline on a small dataset."
                ),
                "hypothesis_zh": "在小规模公开数据上，与简单基线相比，该方法或信号至少提升一个离线推荐指标。",
                "observation": shorten(card.get("core_contribution", ""), 300),
                "observation_zh": "",
                "smallest_experiment": template["experiment"],
                "smallest_experiment_zh": template_zh["experiment_zh"],
                "baseline": template["baseline"],
                "baseline_zh": template_zh["baseline_zh"],
                "dataset_or_setup": dataset_or_setup,
                "dataset_or_setup_zh": translate_dataset_setup(dataset_or_setup),
                "metric": template["metric"],
                "metric_zh": template_zh["metric_zh"],
                "expected_runtime": "< 30 minutes on a laptop CPU for a toy version",
                "expected_runtime_zh": "笔记本 CPU 上运行玩具版本预计少于 30 分钟",
                "failure_modes": [
                    "offline metric lift does not reproduce",
                    "gain appears only on popularity-heavy users/items",
                    "added complexity increases latency or instability",
                ],
                "failure_modes_zh": [
                    "离线指标提升无法复现",
                    "收益只出现在高流行度用户或物品",
                    "复杂度增加导致延迟或稳定性变差",
                ],
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


def translate_dataset_setup(value: str) -> str:
    translations = {
        "MovieLens-1M converted to user sequences, or synthetic sessions": "将 MovieLens-1M 转为用户行为序列，或使用合成会话",
        "Amazon review subset with text metadata, or a tiny image/text item catalog": "带文本元数据的 Amazon 评论子集，或小型图像/文本物品目录",
        "synthetic logged bandit feedback with known propensities": "带已知倾向得分的合成 bandit 日志反馈",
        "MovieLens-small or a synthetic implicit-feedback matrix": "MovieLens-small 或合成隐式反馈矩阵",
        "taobao": "淘宝数据",
    }
    return translations.get(value, "小型公开数据集或合成隐式反馈数据")


def has_chinese_text(value: Any) -> bool:
    if isinstance(value, str):
        return bool(re.search(r"[\u3400-\u9fff]", value))
    return False


def zh_text(value: Any, pending: str) -> str:
    return value.strip() if has_chinese_text(value) else pending


def zh_title(card: dict[str, Any]) -> str:
    return zh_text(card.get("title_zh"), "中文标题待补充")


def zh_list(card: dict[str, Any], field: str, source_field: str, pending: str) -> list[str]:
    translated = card.get(field)
    if isinstance(translated, list) and translated and any(has_chinese_text(item) for item in translated):
        return [str(item) for item in translated]
    source = card.get(source_field) or []
    if field == "methods_zh" and source:
        return [METHOD_LABELS_ZH.get(str(item).lower(), "方法说明待补充") for item in source]
    return [pending] if source else []


def zh_action(card: dict[str, Any]) -> str:
    return zh_text(card.get("recommended_action_zh"), ACTION_LABELS_ZH.get(card.get("recommended_action"), "行动建议待补充"))


def zh_reason(card: dict[str, Any]) -> str:
    translated = card.get("deep_read_reason_zh")
    if has_chinese_text(translated):
        return translated
    topics = [TOPIC_LABELS_ZH.get(topic, topic) for topic in card.get("matched_topics", [])[:3]]
    reasons = [f"与{ '、'.join(topics) }相关" if topics else "与推荐算法的直接关联仍需核验"]
    if card.get("relevance_score", 0) >= 3.5:
        reasons.append("相关性较高")
    if card.get("novelty_score", 0) >= 3.0:
        reasons.append("包含明确的新颖性线索")
    if card.get("implementation_difficulty", 5) <= 3.0:
        reasons.append("适合先做小型实验")
    return "；".join(reasons) + f"（实现难度 {card.get('implementation_difficulty', '待评估')}/5）"


def zh_experiment(card: dict[str, Any]) -> dict[str, str]:
    translated = card.get("possible_experiments_zh")
    if isinstance(translated, list):
        for item in translated:
            if isinstance(item, dict) and has_chinese_text(item.get("experiment_zh")):
                return {
                    "experiment_zh": str(item.get("experiment_zh", "")),
                    "baseline_zh": str(item.get("baseline_zh", "基线方案待补充")),
                    "metric_zh": str(item.get("metric_zh", "评估指标待补充")),
                }
    return {
        "experiment_zh": "小型实验方案待补充",
        "baseline_zh": "基线方案待补充",
        "metric_zh": "评估指标待补充",
    }


def zh_related_reading(card: dict[str, Any]) -> list[str]:
    translated = card.get("related_reading_zh")
    if isinstance(translated, list) and translated:
        rendered: list[str] = []
        for item in translated:
            if isinstance(item, dict) and has_chinese_text(item.get("title_zh")):
                title = item["title_zh"]
                relation = item.get("relation_zh") or "相关方法与背景"
                url = item.get("url", "")
                rendered.append(f"[{title}]({url})（{relation}）")
        if rendered:
            return rendered
    if card.get("related_reading"):
        return ["相关文献中文说明待补充"]
    return []


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
        return f"{icon} 建议：{zh_action(card)}"

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
    translation_gaps = missing_translation_fields(cards, ideas)
    lines: list[str] = []
    lines.append(f"# 推荐算法研究日报 - {output_date}")
    lines.append("")
    if translation_gaps:
        lines.append(f"> 翻译状态：有 {len(translation_gaps)} 个中文字段待补充；中文位置不会回退显示英文。")
    else:
        lines.append("> 翻译状态：中文优先字段已完成校验；英文原文保留在原文/证据字段中供核验。")
    lines.append(f"> 新增窗口：{window_label}；日报精选上限：{report_limit} 项。")
    if repeated_cards and not include_seen:
        lines.append(f"> 已自动去重：{len(repeated_cards)} 项此前已出现在日报中；可用 `--include-seen` 重新展示。")
    lines.append("")
    lines.append("## Executive Answer")
    lines.append("")
    if new_cards:
        lines.append(
            f"本窗口新增 {len(new_cards)} 项与推荐算法相关的论文或业界文章，"
            f"其中 {len(deep_reads)} 项适合深读或尝试实验。"
        )
        first = deep_reads[0] if deep_reads else new_cards[0]
        lines.append(
            f"优先阅读：[{zh_title(first)}]({first['url']})；"
            f"原文标题：{first['title']}；原因：{zh_reason(first)}"
        )
    else:
        lines.append("本窗口没有抓到足够相关的内容，请检查来源状态或适当扩大时间窗口。")
    lines.append("")
    lines.append("## 来源覆盖")
    lines.append("")
    for key in sorted(counts):
        lines.append(f"- {key}: {counts[key]}")
    blocking_errors = [error for error in errors if error.startswith("error:")]
    warnings = [error for error in errors if not error.startswith("error:")]
    if blocking_errors:
        lines.append("- 来源错误：")
        for err in blocking_errors:
            lines.append(f"  - {err}")
    else:
        lines.append("- 来源错误：无")
    if warnings:
        lines.append("- 来源备注：")
        for warning in warnings:
            lines.append(f"  - {warning}")
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
                f"- [{zh_title(card)}]({card['url']}) — "
                f"{card['source_name']}；{zh_action(card)}"
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
        lines.append("### 文章结构化摘要")
        lines.append("")
        industry_cards = sorted(
            (c for c in new_cards if c["source_type"] == "industry"),
            key=lambda c: c["priority_score"],
            reverse=True,
        )
        for card in industry_cards[:8]:
            summary = zh_text(card.get("abstract_or_excerpt_zh"), "中文摘要待补充；请打开原文核验。")
            contribution = zh_text(card.get("core_contribution_zh"), "中文核心贡献待补充。")
            methods = zh_list(card, "methods_zh", "methods", "方法说明待补充")
            lines.append(f"#### {zh_title(card)}")
            lines.append(f"- 原始标题：{card['title']}")
            lines.append(f"- 来源：{card['source_name']}；发布时间：{card.get('published') or '未标注'}")
            lines.append(f"- 原始链接：[{card['url']}]({card['url']})")
            lines.append(f"- 中文摘要：{summary}")
            lines.append(f"- 核心贡献/可借鉴：{contribution}")
            lines.append(f"- 方法/关键机制：{', '.join(methods) if methods else '未从摘要中提取'}")
            lines.append(f"- {score_line(card)}")
            lines.append(f"- {action_line(card)}")
            lines.append("")
    else:
        lines.append("- 本窗口没有相关的大厂文章卡片。")
    lines.append("")
    lines.append("## 🏛️ 历史精选")
    lines.append("")
    if historical_cards:
        for idx, card in enumerate(historical_cards[:4], 1):
            lines.append(f"{idx}. [{zh_title(card)}]({card['url']})")
            lines.append(f"   - 来源：{card['source_name']}（历史精选）")
            lines.append(f"   - 原因：{zh_reason(card)}")
    else:
        lines.append("暂无历史精选。")
    lines.append("")
    lines.append("## 📚 论文深读队列")
    lines.append("")
    queue = paper_deep_reads[:8] or [c for c in top_cards if c["source_type"] != "industry"][:5]
    if not queue:
        lines.append("暂无论文深读候选。")
    for idx, card in enumerate(queue, 1):
        lines.append(f"{idx}. [{zh_title(card)}]({card['url']})")
        lines.append(f"   - 原文标题：{card['title']}")
        lines.append(f"   - 来源：{card['source_name']}（{card['source_type']}）")
        lines.append(f"   - {score_line(card)}")
        lines.append(f"   - {action_line(card)}")
        lines.append(f"   - 原因：{zh_reason(card)}")
    lines.append("")
    lines.append("## 📝 业界文章深读队列")
    lines.append("")
    industry_queue = sorted(
        (c for c in new_cards if c["source_type"] == "industry"),
        key=lambda c: c["priority_score"],
        reverse=True,
    )
    if not industry_queue:
        lines.append("本窗口没有达到深读阈值的业界文章；相关条目仍见上方“大厂技术文章覆盖”。")
    for idx, card in enumerate(industry_queue[:8], 1):
        summary = zh_text(card.get("abstract_or_excerpt_zh"), "中文摘要待补充；请打开原文核验。")
        contribution = zh_text(card.get("core_contribution_zh"), "中文核心贡献待补充。")
        lines.append(f"{idx}. [{zh_title(card)}]({card['url']})")
        lines.append(f"   - 来源：{card['source_name']}")
        lines.append(f"   - 摘要：{summary}")
        lines.append(f"   - 核心贡献/可借鉴：{contribution}")
        lines.append(f"   - {score_line(card)}")
        lines.append(f"   - {action_line(card)}")
        lines.append(f"   - 原因：{zh_reason(card)}")
    lines.append("")
    lines.append("## 🗂️ 论文结构化卡片")
    lines.append("")
    for card in top_cards:
        lines.append(f"### {zh_title(card)}")
        lines.append("")
        lines.append(f"- 原文标题：{card['title']}")
        lines.append(f"- 原始链接：{card['url']}")
        lines.append(f"- 中文摘要：{zh_text(card.get('abstract_or_excerpt_zh'), '中文摘要待补充；请打开原文核验。')}")
        lines.append(f"- 核心贡献：{zh_text(card.get('core_contribution_zh'), '中文核心贡献待补充。')}")
        methods = zh_list(card, "methods_zh", "methods", "方法说明待补充")
        limitations = zh_list(card, "limitations_zh", "limitations", "局限性说明待补充")
        future = zh_list(card, "future_directions_zh", "future_directions", "未来方向说明待补充")
        lines.append(f"- 方法：{', '.join(methods) if methods else '未从摘要中提取'}")
        lines.append(f"- 局限性：{'；'.join(limitations) if limitations else '未明确说明'}")
        lines.append(f"- 未来方向：{'；'.join(future) if future else '未明确说明'}")
        if card.get("related_reading"):
            related = zh_related_reading(card)
            lines.append("- 拓展阅读：" + ("；".join(related) if related else "相关文献中文说明待补充"))
        lines.append(
            "- 数据集/基准："
            + (", ".join(zh_list(card, "datasets_or_benchmarks_zh", "datasets_or_benchmarks", "数据集说明待补充")) if card["datasets_or_benchmarks"] else "未明确说明")
        )
        lines.append(f"- 主题：{', '.join(TOPIC_LABELS_ZH.get(topic, topic) for topic in card['matched_topics']) if card['matched_topics'] else '未明确匹配'}")
        lines.append(f"- 证据：{'；'.join(card['evidence']) if card['evidence'] else '来源元数据有限'}")
        if card["possible_experiments"]:
            experiment = zh_experiment(card)
            lines.append(f"- 小型实验：{experiment['experiment_zh']}")
        lines.append("")
    lines.append("## 💡 研究创意与小型实验")
    lines.append("")
    if not ideas:
        lines.append("本窗口没有生成有明确来源依据的小型实验创意。")
    for idx, idea in enumerate(ideas, 1):
        lines.append(f"{idx}. {zh_text(idea.get('title_zh'), '实验标题待补充')}")
        lines.append(f"   - 假设：{zh_text(idea.get('hypothesis_zh'), '实验假设待补充')}")
        lines.append(f"   - 观察：{zh_text(idea.get('observation_zh'), '动机说明待补充')}")
        lines.append(f"   - 实验：{zh_text(idea.get('smallest_experiment_zh'), '实验方案待补充')}")
        lines.append(f"   - 基线：{zh_text(idea.get('baseline_zh'), '基线方案待补充')}")
        lines.append(f"   - 数据集/设置：{zh_text(idea.get('dataset_or_setup_zh'), '数据集或实验设置待补充')}")
        lines.append(f"   - 指标：{zh_text(idea.get('metric_zh'), '评估指标待补充')}")
        lines.append(f"   - 预计耗时：{zh_text(idea.get('expected_runtime_zh'), '笔记本 CPU 玩具实验预计少于 30 分钟')}")
        failure_modes = idea.get("failure_modes_zh")
        if not isinstance(failure_modes, list) or not any(has_chinese_text(item) for item in failure_modes):
            failure_modes = ["离线指标提升无法复现", "收益只出现在高流行度用户或物品", "复杂度增加导致延迟或稳定性变差"]
        lines.append(f"   - 失败模式：{'；'.join(str(item) for item in failure_modes)}")
    lines.append("")
    lines.append("## ✅ 行动计划")
    lines.append("")
    if queue:
        lines.append(f"- 今日深读：{zh_title(queue[0])}")
    if ideas:
        lines.append(f"- 本周尝试：{zh_text(ideas[0].get('title_zh'), '小型实验标题待补充')}")
    track = [c for c in new_cards if c["recommended_action"] == "track"]
    if track:
        lines.append(f"- 后续跟踪：{zh_title(track[0])}")
    if errors:
        lines.append("- 来源补强：检查失败来源，或补充官方会议页面/手工文章链接。")
    else:
        lines.append("- 来源补强：继续补充尚未被订阅源覆盖的顶会页面和大厂文章链接。")
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
        items, errs = fetch_arxiv(
            catalog,
            args.max_results,
            window_start,
            window_end,
            cache_path=args.output_dir / "arxiv-cache.json",
        )
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
    parser.add_argument(
        "--translation-file",
        type=Path,
        help="JSON payload produced by the model translation pass; merged before rendering.",
    )
    parser.add_argument(
        "--require-translations",
        action="store_true",
        help="Return a non-zero status when any required Chinese field is missing.",
    )
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
    if args.translation_file:
        translation_payload = json.loads(args.translation_file.read_text(encoding="utf-8"))
        cards, ideas = apply_translation_payload(cards, ideas, translation_payload)
    translation_gaps = missing_translation_fields(cards, ideas)
    output_date = window_end.astimezone(LOCAL_TZ).date().isoformat()
    report = render_report(cards, ideas, errors, counts, output_date, window_label, args.report_limit, args.include_seen)
    paths = write_outputs(args.output_dir, cards, ideas, report, output_date)
    update_state(cards, state, now_iso())
    save_state(state_path, state)
    paths["state"] = str(state_path)

    print(
        json.dumps(
            {
                "counts": counts,
                "cards": len(cards),
                "ideas": len(ideas),
                "translation_gaps": len(translation_gaps),
                "paths": paths,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if any(error.startswith("error:") for error in errors):
        return 2
    if args.require_translations and translation_gaps:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
