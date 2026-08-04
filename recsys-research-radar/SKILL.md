---
name: recsys-research-radar
description: Track recommendation-system research and industry posts, then turn fresh arXiv papers, top-conference items, and company engineering/research articles into structured paper cards, relevance-ranked reading lists, novelty assessments, small experiment ideas, and daily research reports. Use when the user asks what happened today in recommendation algorithms, which RecSys papers/articles are worth deep reading, or what lightweight experiments to try from recent recommender-system work.
---

# RecSys Research Radar

## Overview

Use this skill as a local-first research radar for recommendation algorithms. Preserve the reference hub's flow:

Collect -> Understand -> Rank -> Generate -> Report

The user-facing result is Chinese. Keep the original title, abstract, claims, and source link for verification, but add Chinese translations for every substantive field. Do not label machine-generated paraphrases as verbatim translations; preserve uncertainty and mark fields as `待人工核验` when the source is too thin.

The default workflow answers three questions:

- What happened recently in recommendation algorithms?
- Which papers or industry posts deserve deep reading?
- What small, reproducible experiment is worth trying next?

## Quick Start

Run the bundled script first when the user wants a daily update:

```bash
python3 recsys-research-radar/scripts/fetch_recsys_research.py --lookback-days 2 --max-results 40
```

The default window is workday-aware: a normal run covers the previous calendar day; a Monday run covers the previous Friday plus the weekend. Use `--window-mode calendar --lookback-days N` for an explicit rolling window. The report shows at most 8 curated new items by default; JSON keeps the full result set. Use `--report-limit N` to change that cap.

The default output directory also contains `radar-state.json`, which records first/last seen times and suppresses already reported items from later daily sections. Use `--include-seen` for an audit or repeat-reading run.

ArXiv collection is resilient to intermittent network failures: it splits long keyword filters into short queries, tries both `export.arxiv.org` and `arxiv.org`, then uses OpenAlex's arXiv-linked metadata, an optional Semantic Scholar API-key path, and finally `arxiv-cache.json`. Reports must label fallback or cached items and must not present cached metadata as newly published. A recovered fallback is a warning, not a failed run; only exhaustion of all fallbacks is an error.

If network access is unavailable or a deterministic smoke test is needed:

```bash
python3 recsys-research-radar/scripts/fetch_recsys_research.py --offline-sample --output-dir recsys-research-radar/output
```

Read the generated markdown report and JSON cards before answering. Do not claim an item is current unless it appears in the fetched output or was independently verified during the current turn.

After reading the artifacts, complete the translation pass before presenting results. The fetcher output is an intermediate artifact, not a user-facing report:

- translate each selected item's title, abstract/excerpt, core contribution, methods, claims, datasets/benchmarks, deep-read reason, recommended action, and possible experiment into Chinese;
- present Chinese first and retain the original English in a secondary note or an `原文` line when useful;
- translate research ideas and the daily report's executive answer, queue, novelty notes, and action plan into Chinese;
- keep names of methods, datasets, metrics, and venue names in English in parentheses on first mention;
- never translate away evidence: preserve exact numbers, metric names, URLs, and quoted claims.

Use the deterministic translation pass so the result is written to disk and checked before Pages is built:

```bash
python3 recsys-research-radar/scripts/translation_pass.py \
  --cards /path/to/cards-YYYY-MM-DD.json \
  --ideas /path/to/ideas-YYYY-MM-DD.json \
  --template /path/to/translations-YYYY-MM-DD.json
```

Fill the template with Chinese values keyed by card ID and idea index, then rerun the fetch command with `--translation-file /path/to/translations-YYYY-MM-DD.json --require-translations`. A missing Chinese field must fail validation; the renderer must never silently substitute English into a Chinese field.

## Source Strategy

Use `references/source_catalog.json` as the editable source registry.

Default sources:

- arXiv: `cs.IR`, `cs.LG`, `cs.AI`, `stat.ML`, filtered by recommender keywords.
- Adjacent arXiv signals: information retrieval/search ranking, ads ranking/CTR/CVR, and LLM/RAG/agent work when the method has a clear transfer path to recommendation.
- OpenReview: configurable venue IDs for conference submissions, abstracts, authors, public dates, decisions, and forum links. The current API 2 requires `OPENREVIEW_ACCESS_TOKEN`; without it, skip OpenReview cleanly and use the official conference portal/manual URL path instead of repeatedly calling the legacy API.
- RSS/Atom: company research and engineering blogs from major recommender-system practitioners.
- Adjacent industry sources: Google/Microsoft search and ads research, Alibaba/Tencent commercial ranking, and selected LLM/RAG/agent engineering posts. Keep them in a separate adjacent-signal view when they are not direct recommendation work.
- Official portals: use `official_portals` as discovery surfaces for Chinese big-tech technical sites and developer communities.
- WeChat accounts: use `wechat_accounts` as a monitored registry; public WeChat articles usually have no stable RSS, so ingest a user-provided article URL or a corresponding official-site mirror and preserve the account name as provenance.
- Manual URLs: use when the user provides conference proceedings pages, company posts, X/Twitter threads, WeChat posts, or PDFs that have no stable public feed. The catalog includes verified seed articles from Meituan, ByteDance/Volcengine, and Tencent Cloud.
- Historical picks: use `historical_picks` for a small, clearly labeled set of classic industrial papers/articles. Keep them separate from the current-window ranking and never present them as today's new work.

Treat conference and industry feeds as best-effort adapters. If a conference does not expose a stable API/feed, add the official proceedings or accepted-papers URL to `manual_urls`, fetch/read it in the current session, then include the relevant items in the card pipeline.

Search, advertising, and large-model items are included only when they offer a concrete recommendation transfer point: retrieval/candidate generation, query or item understanding, ranking/reranking, CTR/CVR or multi-objective optimization, auctions/marketplace allocation, user modeling, RAG, agents, or generative recommendation. Exclude generic search-engine news, generic ad-tech news, and general LLM announcements.

For each daily run, report industry coverage by company/source, not only a single RSS total. Every selected industry item must include a Chinese-first summary, original title/link, core contribution or transferable mechanism, evidence limits, scores, and an action recommendation; a bare link is not a valid industry card. Prefer recent official posts; retain older seed articles only as background context and label them as such. When a Chinese portal is JavaScript-rendered or blocks automated access, search the portal in the current session, open the official article page, and pass its URL through `manual_urls` for the card pipeline.

## Card Schema

Every selected item should become a structured card with:

- identity: `id`, `source_type`, `source_name`, `title`, `authors`, `published`, `url`
- bilingual identity/content: `title_zh`, `abstract_or_excerpt`, `abstract_or_excerpt_zh`, `core_contribution_zh`, `methods_zh`, `claims_zh`, `datasets_or_benchmarks_zh`
- research interpretation: `limitations`, `limitations_zh`, `future_directions`, `future_directions_zh`, `related_reading`, `related_reading_zh`
- provenance confidence: `authors`, `author_affiliations`, `author_affiliations_confidence`, `published`, `discovered_at`, `first_seen_at`, `previously_reported`
- substance: `core_contribution`, `methods`, `claims`, `datasets_or_benchmarks`
- research fit: `matched_topics`, `relevance_score`, `novelty_score`, `implementation_difficulty`
- decision: `recommended_action`, `recommended_action_zh`, `deep_read_reason`, `deep_read_reason_zh`, `possible_experiments`, `possible_experiments_zh`
- provenance: `evidence`, `fetched_at`

Use conservative scores. Prefer "track" over "deep_read" when the abstract/post lacks enough evidence.

Recommended actions:

- `ignore`: unrelated or too thin.
- `track`: relevant enough to keep, but not urgent.
- `summarize`: useful context that merits a short note.
- `deep_read`: high relevance or strong novelty with enough evidence.
- `try_experiment`: high relevance and a small local experiment is plausible.

## Ranking Rules

Rank cards by a transparent priority score:

```text
priority = relevance_score * 0.45
         + novelty_score * 0.30
         + industry_or_conference_signal * 0.10
         + experimentability * 0.15
         - implementation_difficulty * 0.12
```

Prioritize items about:

- retrieval, candidate generation, ANN/vector search
- coarse ranking, reranking, multi-stage cascades, latency-quality tradeoffs
- ranking, learning-to-rank, calibration, multitask ranking
- sequential/session recommendation and user modeling
- generative recommendation, LLM agents, RAG for recommender systems
- multimodal recommendation
- graph, knowledge-aware, and social recommendation
- bandits, RL, counterfactual learning, causal evaluation
- debiasing, fairness, privacy, safety, robustness
- online evaluation, A/B testing, long-term value, marketplace/ad ranking
- serving systems, feature stores, real-time personalization, cost/latency tradeoffs

## Idea Generator

Generate research ideas only from cards already produced in this run. Each idea must include:

- title
- Chinese versions of the title, hypothesis, experiment, baseline, setup, metric, and failure modes
- motivating paper/article ID
- falsifiable hypothesis
- smallest experiment
- baseline
- dataset or synthetic setup
- metric
- expected runtime
- failure modes

Prefer small experiments using public or toy data: MovieLens small/1M, Amazon review subsets, MIND-small, KuaiRec, synthetic session logs, or tiny implicit-feedback matrices. Avoid ideas that require proprietary production logs, paid APIs, or multi-GPU training.

## Daily Report

Use the structure in `references/report_schema.md`.

The report must include:

- brief answer to "today in recommendation algorithms"
- today's topic clusters and 2-4 trend observations
- curated new-item queue capped at 5-10 items
- separate paper deep-read and industry-article deep-read queues
- include a compact but structured industry-article section with summaries; do not repeat full industry cards in the paper structured-card section
- clearly labeled historical picks when useful
- novelty notes
- action recommendations
- 3-5 small experiments worth trying
- source errors or coverage gaps

Keep the final user answer short and actionable. Link to the local generated report and mention source limitations when any adapter failed.

## Resources

- `scripts/fetch_recsys_research.py`: fetch sources, build cards, rank items, generate ideas, merge the translation payload, and write a daily markdown report plus JSON artifacts.
- `scripts/translation_pass.py`: create, apply, and validate the model-generated Chinese translation payload.
- `references/source_catalog.json`: editable source registry, topic keywords, conference portals, discovery queries, and topic-tagged historical picks.
- `references/report_schema.md`: report format and scoring rubric.
