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
