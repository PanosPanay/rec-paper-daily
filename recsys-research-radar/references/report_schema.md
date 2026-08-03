# RecSys Daily Research Report Schema

Use this structure for the daily markdown report and for concise user-facing summaries.

## Title

`# 推荐算法研究日报 - YYYY-MM-DD`

Keep the English title in a secondary line when needed: `原文标题: ...`.

## Executive Answer

Answer these directly:

- What happened today or in the requested lookback window?
- Which items are worth deep reading?
- What small experiment should we try first?

Write the answer in Chinese. Include English names in parentheses on first mention.
State the current-window rule and distinguish new items from historical picks.

## Source Coverage

List source counts and failures:

- arXiv papers fetched
- OpenReview/top-conference items fetched
- industry posts fetched
- industry coverage by company/source
- adjacent signals from search, advertising, and LLM/RAG/agent work, with transfer relevance noted
- manual URLs reviewed
- source errors

## Paper Deep-Read Queue

For each top item:

- Chinese title, original title, and link
- source and date
- why it matters, in Chinese
- novelty assessment, in Chinese
- recommended action, in Chinese

## Industry Article Deep-Read Queue

Keep company engineering/research articles in a separate queue from papers. Link each article and include source company, why it matters, novelty assessment, and recommended action.
The preceding industry coverage section should be only a compact index. Do not repeat full industry cards in the paper structured-card section.

## Topic Clusters And Trends

Group the current-window items by topic and summarize 2-4 evidence-backed trends. Treat coarse ranking and reranking as a first-class cluster.
Keep search/information retrieval, ads ranking/CTR/CVR, and LLM/RAG/agent signals visible as adjacent clusters when they provide a concrete recommendation transfer point.

## Historical Picks

Show classic industrial papers/articles in a separate section. Label them as historical and never mix them into the answer to "what happened today".

## Structured Cards

Render compact cards with:

- Chinese translation first, followed by the original when useful
- core contribution
- methods
- explicit claims
- limitations and future directions
- related reading with the relationship explained
- datasets or benchmarks
- matched topics
- relevance, novelty, difficulty
- possible experiment

## Research Ideas

Each idea must contain:

- Chinese title and hypothesis
- source item
- smallest experiment, baseline, metric, and failure modes in Chinese

## Action Plan

End with:

- read today
- implement this week
- track for later
- coverage gaps to fix

## Scoring Rubric

Relevance:

- 0-1 unrelated or only generic ML
- 2 weak background relevance
- 3 useful recommender-system method or evaluation idea
- 4 directly relevant to recommendation algorithm research
- 5 central to retrieval/ranking/personalization work

Novelty:

- 0-1 survey, recap, or implementation detail
- 2 incremental change
- 3 clear method, system, dataset, or evaluation contribution
- 4 strong new direction or production evidence
- 5 rare, well-evidenced shift in method or practice

Implementation difficulty:

- 0-1 toy or notebook-scale
- 2 local CPU experiment
- 3 single GPU or nontrivial engineering
- 4 multi-GPU, large data, or complex infra
- 5 proprietary data, production system, or unavailable platform
