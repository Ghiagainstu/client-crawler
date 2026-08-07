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

## 新增客户
1. 在 `crawler/parsers/` 新建 `<client>.py`，实现 `parse_list(html)->list[{title,url,date_raw,summary}]` 与 `parse_article(html)->{content, article_title}`。
2. 在 `crawler/parsers/__init__.py` 的 `REGISTRY` / `BASE_URL` 注册。
3. 在 `config/sites.yaml` 增加该客户条目。

## Notion 同步（可选）
设置环境变量后加 `--notion` 即推送：
```bash
export NOTION_TOKEN="ntn_xxx"            # 内部集成密钥，勿硬编码
export NOTION_DATABASE_ID="xxxxxxxx"
python cli.py --client sasol --notion
```
要求：Notion 集成对该 database 有 Insert 权限；目标库属性含 `Name/Client/Published/Media Source/Source URL`。

## 部署到 Ubuntu 192.168.0.147
仓库自带一键部署包（`deploy/`），含 venv 安装、`.env` 密钥模板、systemd timer：

```bash
# 1) 把整个仓库传到服务器（任选其一）
scp -r . deploy@192.168.0.147:/opt/client-crawler        # 或用 git clone / tarball
ssh deploy@192.168.0.147

# 2) 在服务器上执行（root 会自动装 systemd 定时器；非 root 仅装 venv + 提示 cron）
sudo bash /opt/client-crawler/deploy/install.sh /opt/client-crawler deploy
```

`install.sh` 会：建 venv → 装依赖 → 生成 `.env`（600 权限，填 Notion 密钥）→ 冒烟测试 →（root）启用每周一 09:00 的 `client-crawler.timer`。

- 非 root / 不想用 systemd：用 cron 替代
  ```cron
  0 9 * * 1  cd /opt/client-crawler && /opt/client-crawler/venv/bin/python cli.py --client sasol --notion >> /var/log/crawler.log 2>&1
  ```
- 看板读取 `data/<client>/*.json` 生成每周汇总。
- 改频率：编辑 `deploy/client-crawler.timer` 的 `OnCalendar` 后 `systemctl daemon-reload`。

## 合规
- 默认尊重 `robots.txt`（`core.py` 中 `check_robots`）。
- 文章抓取间隔默认 1s，避免压垮对方服务器。
- 仅抓取已授权/公开站点。
