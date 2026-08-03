# 推荐算法研究日报 Pages

日报仍以 Obsidian/坚果云目录为主存储；`scripts/build_pages.py` 将其中的 `daily-*.md` 转成静态归档页，写入 `site/`。

## 本地同步

```bash
python3 recsys-research-radar/scripts/build_pages.py
git add recsys-research-radar/site
git commit -m "更新推荐算法研究日报"
git push
```

GitHub Actions 会在推送到 `main` 后自动部署 GitHub Pages。首次使用时，在仓库 Settings → Pages → Build and deployment 中选择 GitHub Actions。

## 来源凭证

OpenReview 当前 API 2 需要访问令牌。没有配置时日报会跳过 OpenReview，并保留官方顶会入口，不会把该可选来源标记为主流程失败：

```bash
export OPENREVIEW_ACCESS_TOKEN="你的 OpenReview access token"
```

arXiv 会拆分查询并轮换两个官方域名；若运行环境 DNS 或外网暂时不可达，会依次尝试 OpenAlex、可选的 Semantic Scholar API key 和本地缓存，并在日报中标注实际使用的来源。
