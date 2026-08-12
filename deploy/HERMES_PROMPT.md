# Hermes 部署 Prompt（client-crawler）

> 复制下面整段，发给运行在 `192.168.0.147` 上的 hermes agent 即可。

```
角色：你是部署 agent，运行在 Ubuntu 主机 192.168.0.147。
任务：一次性部署 client-crawler 新闻爬虫并配置每周定时任务。部署后由系统定时器自动运行，无需 AI 常驻。

代码来源：
git clone https://github.com/Ghiagainstu/client-crawler.git /opt/client-crawler
（若你的 GitHub 登录名不是 Ghiagainstu，替换为实际 clone URL）

步骤：
1. cd /opt/client-crawler
2. python3 -m venv venv && venv/bin/pip install -r requirements.txt
   若需爬 Akamai/bot-WAF 保护的站点（如 hitachi-hightech，sites.yaml 标 engine: playwright +
   browser_channel: chrome），需两步：(1) 下载 patchright 内核 venv/bin/python -m patchright
   install chromium；(2) 在 Ubuntu 装真实 Chrome 供 channel 驱动：sudo apt-get install -y
   google-chrome-stable（否则 Akamai 仍按 TLS 指纹拦截 patchright 自带的 chromium）。
2b. 配置 S: 归档路径（原始数据 + Client Knowledge Base 落盘）：
    cp deploy/.env.example .env
    打开 .env，确认 S_DRIVE_ROOT 指向本机 S: 共享的本地目录
    （默认 /media/theeggsh/SSD-2/AI-Report，即 Windows 映射的 S: 盘）。
    爬虫每周一把原始数据写 S:/<client>/<category>/<date>.json，
    KB 骨架写 S:/Obsidian/<client>/KB/。目录需爬虫服务账户可写（默认 777 已满足）。
3. 冒烟测试：venv/bin/python cli.py --client sasol --limit 2
   确认生成 data/sasol/*.json 且含 title / published_at / content；
   同时应在 S_DRIVE_ROOT 下看到 sasol/ 与 Obsidian/sasol/KB/ 目录结构生成。
4. 定时任务 + 看板（默认 systemd）：
   cp deploy/client-crawler.service deploy/client-crawler.timer deploy/crawler-check.service deploy/crawler-check.timer deploy/dashboard.service /etc/systemd/system/
   systemctl daemon-reload && systemctl enable --now client-crawler.timer crawler-check.timer dashboard.service
   - client-crawler.timer：**每月 1 号 09:00** 跑 deploy/run_weekly.sh（爬全部已接入客户 + 生成看板 + 写 S: 盘）。已由每周改为每月。
   - crawler-check.timer：**每月 1 号 19:00** 跑 deploy/check_queue_and_crawl.sh（纯代码，**不调 AI**）。
     它读 S: 盘队列 `_crawler_queue/requests/<客户>.json`，对「已被 WorkBuddy 写好解析器、
     已加入 config/sites.yaml」的客户爬一次（用 `_crawler_queue/processed/<客户>.marker` 做幂等
     去重，agent 改了录入才重爬）；未接入的客户跳过，留给 agent。爬完重建看板 + 状态。
   - dashboard.service：在 0.0.0.0:8082 跑 dashboard/server.py（Flask）；并读取 .env 里的
     S_DRIVE_ROOT，使 /submit 录入能同步到 S: 盘队列。团队访问
     http://192.168.0.147:8082 看新闻汇总；页头「＋ 添加爬虫」→ /add 填表加新客户；
     另有「🗂️ 全站结构」标签页（全站爬后自动出现）与 `/ai-report/` 路由（绿龙虾 AI 报告）。
     注意：端口 8080 已被 nginx 占用（之前部署的 "AI-Report" 客户每周新闻情报看板，
     静态服务），故 Flask 改用 8082，不要改回 8080（会 Address already in use 启动失败）。
     8080 的 AI-Report 页已加「🟢 绿龙虾·全站 AI 分析」按钮，链接到 8082 的 /ai-report/。
     提交后服务器把录入同步到 S: 盘队列（S_DRIVE_ROOT/_crawler_queue），由 WorkBuddy 侧的
     「火哥的绿龙虾」直接从局域网共享读取并接手写解析器、再 push 代码让服务器 pull 爬取。
     数据/录入不再经过 GitHub。
   - 依赖：requirements.txt 已含 flask>=3.0，install.sh 第 30 行已 pip 安装；无需额外操作。
   （全量新闻爬频率在 deploy/client-crawler.timer 的 OnCalendar=*-*-01 09:00:00；
    提交检查在 deploy/crawler-check.timer 的 OnCalendar=*-*-01 19:00:00，均为系统本地时区、每月一次。）
5b. （一次性）全站结构化爬取排期：全站爬默认不在定时器里，由一次性 at 任务触发。
    写一个包装脚本确保 S_DRIVE_ROOT 注入（at 任务不加载 .env，必须手动 source）：
    cat > /tmp/sitecrawl.sh <<'EOF'
    #!/bin/bash
    cd /opt/client-crawler
    set -a; [ -f .env ] && . ./.env; set +a
    exec venv/bin/python cli.py --client sasol --mode site
    EOF
    chmod +x /tmp/sitecrawl.sh
    echo "/tmp/sitecrawl.sh" | at 19:00 08/14/2026
    （爬完 cli.py 自动 dash_build.main() 重建 8082，新增「🗂️ 全站结构」tab；同时写 S: 盘
     <client>/site/，供周一 WorkBuddy 绿龙虾自动化读取做 AI 分析。改日期即改排期，atq/atrm 管理。）
5. GitHub 仅用于「代码分发」：WorkBuddy 侧 push parser/config 改动，服务器 git pull 拉取
   （run_weekly.sh 第一步）。爬取数据、KB、录入队列全部走 S: 盘，不再 push 任何数据到 GitHub，
   故服务器无需 github.com 的 push 凭证（只需能 git pull 代码即可；若 pull 也不通，可由 hermes
   手动 rsync 代码，见约束）。
6. （可选）配置企业微信告警：在 .env 填 WECOM_WEBHOOK=（群机器人 webhook），
   周跑若有客户抓到 0 条会自动推送告警。不需要可留空。
7. 汇报：部署结果、冒烟测试条数、下次运行时间。

注意：
- Notion 同步由另一侧的 WorkBuddy（已连 Notion MCP）负责，你无需处理 token 或 MCP。
- 后续 HTML 看板也承载在这台机上，团队通过局域网访问。
约束：遵守 robots.txt，代码内已限速（article_delay=1s），不泄露任何密钥。
```

---

## 架构说明（给你参考）
- **Ubuntu（hermes）**：**每月 1 号 09:00** 跑 `run_weekly.sh` → 抓全部已接入客户 → `data/` + 写 S: 盘（`kb_export`）+ 生成看板 + 写 `status.json`（运行状态）。另外**每月 1 号 19:00** 跑 `check_queue_and_crawl.sh`（纯 bash，**不调 AI**）→ 读 S: 盘提交队列，对「已接入」的新客户爬一次并重建看板。两者均已由每周/一三五改为**每月一次**。全站结构化爬取（`--mode site`）为一次性 `at` 任务（见 HERMES 步骤 5b），默认排在本周五 19:00。数据 / KB / 录入队列全部落 S: 盘，**不经过 GitHub**。GitHub 仅在脚本第一步 `git pull` 拉最新代码。
- **WorkBuddy（Notion MCP / AI）**：每周一 10:00 直接读取 S: 盘上的 `data/`（S_DRIVE_ROOT 局域网共享，WorkBuddy 侧可达），调用 Notion MCP 把新条目写入数据库 **客户每周新闻汇总**（ID `8c48dd185e224af4ac7237e98ae1a86e`），按 `source_url` 去重；并读取 S: 盘队列 `S_DRIVE_ROOT/_crawler_queue/queue.jsonl` 接手新录入。服务器不需要任何 Notion 密钥。
- **「火哥的绿龙虾」全站 AI 分析（WorkBuddy 自动化，每周一 10:00）**：读取 `S_DRIVE_ROOT/<client>/site/` 最新全站数据（全站爬产出），AI 抽取写入 `S_DRIVE_ROOT/Obsidian/<client>/KB/` 的 **同名现有文件**（00-Index.md / 01-Facts-产品事实层.md / 02-Selling-Points-卖点主张层.md / 03-Compliance-合规层.md，追加带日期小节、不覆盖 `status: approved` 段落），并生成自包含报告 `S_DRIVE_ROOT/<client>/site/<日期>_ai_report.html`（+ `.md`）。该报告由 8082 的 `/ai-report/` 路由读出，8080 AI-Report 页的「🟢 绿龙虾·全站 AI 分析」按钮即跳转到此。
- **S: 盘归档 + KB 骨架**：每次爬取后 `kb_export` 把原始数据写 `S_DRIVE_ROOT/<client>/<category>/<date>.json`，并在 `S_DRIVE_ROOT/Obsidian/<client>/KB/` 生成 00-Index / 01-Facts-产品事实层 / 02-Selling-Points-卖点主张层 / 03-Compliance-合规层 骨架文件（idempotent，不覆盖已有内容）。AI 抽取事实/卖点填入 01/02 由 WorkBuddy 侧（绿龙虾自动化）完成，服务器不调 LLM。
- S_DRIVE_ROOT 通过 `.env`（gitignored）注入，client-crawler.service 与 dashboard.service 均用 `EnvironmentFile=-.../.env` 读取。**注意**：一次性 `at` 全站爬任务不加载 `.env`，必须按步骤 5b 在脚本里 `set -a; . ./.env` 注入 S_DRIVE_ROOT，否则爬虫只写本地 `data/`、不写 S: 盘，绿龙虾自动化会找不到全站数据。
- **运行状态监控**：`run_weekly.sh` 末尾写 `status.json`（last_run / 各客户条数 / 0 条告警），8082 看板页头显示「上次运行时间 + 条数」，任一客户 0 条标红提醒；若配了 `WECOM_WEBHOOK` 还会推企业微信。
- **全站结构化入库（site 模式）**：`python cli.py --client <客户> --mode site [--limit N]`。它会发现全站 URL（先读 robots.txt 里的 Sitemap，没有就 BFS 爬，遵守 robots.txt + 限速），按 URL 路径第一段归类板块（可在 sites.yaml 用 `site_sections` 把路径段映射成友好名，如 `our-businesses: 业务`），逐页抽正文，输出到 `S_DRIVE_ROOT/<client>/site/<日期>.json`（按板块分组全文）+ `<日期>_index.json`（板块→页标题/链接清单，直接回答「网站有什么」）+ `<日期>_index.md`（人读大纲）。`site_max_pages`（默认 500）、`site_delay`、`site_max_depth` 在 sites.yaml 可调。爬完自动 `dash_build.main()` 重建 8082（新增「🗂️ 全站结构」tab）。由一次性 `at` 任务触发（步骤 5b），不在常驻定时器里。

## 你（火哥）要确认
- hermes 跑完部署后，第一次 `run_weekly.sh` 能在 S: 盘生成 `sasol/news/<日期>.json` 与 `Obsidian/sasol/KB/` 四层文件（否则 WorkBuddy 收不到数据）。GitHub push 已不再需要（数据走 S: 盘）；仅需确认服务器 `git pull` 能拉到代码（若不通，代码更新改由 hermes rsync）。
- 看板（团队 LAN 访问）已含「添加爬虫」菜单（dashboard/server.py，Flask）；若 hermes 是早期按旧 prompt 部署、看板还是 `python -m http.server`，需重跑一次 install.sh 让 dashboard.service 改用 server.py 并装上 flask。
- 看板页头出现「上次运行 … ｜ 条数 …」即代表监控已生效；若显示空白说明 `run_weekly.sh` 尚未跑过（status.json 未生成）。
