# Client News Crawler

抓取客户网站新闻/文章，归一化为标准 JSON，供「每周新闻汇总看板」使用，并可选同步 Notion。
首个接入客户：**Sasol**（`https://www.sasol.com/media-centre/media-releases`）。

## 目录结构
```
client-crawler/
├── config/sites.yaml        # 客户站点配置（list_url / parser / 抓取策略）
├── crawler/
│   ├── core.py              # 通用抓取：重试 / 限速 / robots 检查
│   ├── pipeline.py          # 归一化标准 schema + 去重
│   ├── parsers/
│   │   └── sasol.py         # Sasol 列表 + 文章解析器
│   └── notion_sync.py       # Notion 同步（读环境变量密钥）
├── cli.py                   # 入口：python cli.py --client sasol
├── data/<client>/<date>.json  # 输出
├── onboard/
│   ├── app.py               # 网页录入表单（Flask，本地 :8765）
│   ├── process_queue.py     # Agent 接手：把待处理提交脚手架化为解析器+配置
│   └── inspect_site.py      # Agent 辅助：分析列表页、给出候选选择器
└── requirements.txt
```

## 本地运行
```bash
# 首次安装依赖（已建 venv 在 ~/.workbuddy/binaries/python/envs/default）
python -m pip install -r requirements.txt

# 抓取 Sasol 全部新闻 + 全文
python cli.py --client sasol

# 仅前 5 条（调试用）
python cli.py --client sasol --limit 5

# 只抓列表+摘要，不抓正文
python cli.py --client sasol --no-articles
```

## 配置（config/sites.yaml）
```yaml
clients:
  sasol:
    name: Sasol
    parser: sasol
    list_url: https://www.sasol.com/media-centre/media-releases
    media_source: Sasol Media Centre
    media_source_url: https://www.sasol.com/media-centre/media-releases
    fetch_articles: true   # 混合模式：同时抓全文
    article_delay: 1.0     # 文章间请求间隔（秒，礼貌限速）
    limit: 0               # 0 = 不限
```

## 新增客户：网页自助录入 + Agent 接手（推荐）

模式：人在网页填字段 → 提交进入队列 → 「火哥的绿龙虾」接手写解析器、跑爬虫、同步看板与 Notion。

```
人（填表）                Agent（火哥的绿龙虾）
─────────                ────────────────────
打开录入页 :8765         运行 onboard/process_queue.py
  填写 site 字段   ──▶     · 生成 crawler/parsers/<client>.py（含 TODO 选择器）
  点提交                  · 写入 config/sites.yaml
                          · 注册 crawler/parsers/__init__.py
                          · 队列项标记 registered
                        运行 onboard/inspect_site.py <client> 定选择器
                        python cli.py --client <client> --limit 3 --no-articles  # 冒烟
                        python cli.py --client <client>  # 正式抓 + 同步
```

1. 启动录入页（本地 / 服务器均可）：
   ```bash
   python onboard/app.py          # http://localhost:8765
   ```
2. 必填：客户标识（英文小写）、显示名、网站根地址、新闻列表页 URL；
   选填：来源媒体名/链接、是否抓全文、频率、备注（备注里写清“列表是 JS 动态 / 需翻页 / 子域名”等，能帮我更快写对解析器）。
3. Agent 接手（我来处理）：
   ```bash
   python onboard/process_queue.py   # 把 pending 提交脚手架化
   python onboard/inspect_site.py <client>   # 输出候选 ITEM_SELECTOR
   ```
4. 我补全解析器里的 TODO 选择器后，跑爬虫并同步。

> 备注：`onboard/queue.jsonl` 与 `onboard/requests/` 为运行时数据，已在 `.gitignore` 忽略；
> 录入页与 `process_queue.py` / `inspect_site.py` 脚本均入库。

## 新增客户（纯手动，备选）
1. 在 `crawler/parsers/` 新建 `<client>.py`，实现 `parse_list(html)->list[{title,url,date_raw,summary}]` 与 `parse_article(html)->{content, article_title}`。
2. 在 `crawler/parsers/__init__.py` 的 `REGISTRY` / `BASE_URL` 注册。
3. 在 `config/sites.yaml` 增加该客户条目。

## Notion 同步（由 WorkBuddy 侧完成，使用 Notion MCP）
Notion MCP 仅连接在 WorkBuddy（本机），不在 Ubuntu 服务器，因此同步在 WorkBuddy 跑：

- 目标库（已建，工作区根目录）：**客户每周新闻汇总**
  - 数据库 ID：`8c48dd185e224af4ac7237e98ae1a86e`
  - data_source_id：`8a95ff01-605f-4fe7-9399-a9a5d68d5d29`
  - 属性：标题 / 客户 / 发布日期 / 来源媒体(URL) / 原文链接(URL) / 摘要 / 抓取时间
- 数据流：Ubuntu 爬虫产出 `data/<client>/*.json` → `run_weekly.sh` 推回 GitHub → WorkBuddy 定时 `git pull` 并调用 Notion MCP 写入（按 `source_url` 去重）。
- 已配置 WorkBuddy 自动化「client-crawler Notion sync」（每周一 10:00）自动执行上述同步。
- 旧版 `crawler/notion_sync.py`（读 `NOTION_TOKEN` 环境变量）保留作离线兜底，默认不走它。

## 部署到 Ubuntu 192.168.0.147（hermes agent）
代码已推到 GitHub 私有仓 `https://github.com/Ghiagainstu/client-crawler`。
给 hermes 的部署 prompt 见 `deploy/HERMES_PROMPT.md`（复制整段发给 hermes 即可）。

要点：
- hermes `git clone` → 建 venv → systemd timer 每周一 09:00 跑 `deploy/run_weekly.sh`。
- `run_weekly.sh`：抓 Sasol 新闻 → 把 `data/` force-add 并 `git push` 回 GitHub。
- **服务器不碰 Notion token**：同步由 WorkBuddy 侧完成（见上）。
- 要求：服务器对 github.com 有 push 凭证（deploy key / 用户凭证）。
- 看板读取 `data/<client>/*.json` 生成每周汇总（看板另建）。

## 合规
- 默认尊重 `robots.txt`（`core.py` 中 `check_robots`）。
- 文章抓取间隔默认 1s，避免压垮对方服务器。
- 仅抓取已授权/公开站点。
