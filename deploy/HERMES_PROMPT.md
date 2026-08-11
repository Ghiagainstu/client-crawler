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
   cp deploy/client-crawler.service deploy/client-crawler.timer deploy/dashboard.service /etc/systemd/system/
   systemctl daemon-reload && systemctl enable --now client-crawler.timer dashboard.service
   - client-crawler.timer：每周一 09:00 跑 deploy/run_weekly.sh（爬新闻 + 生成看板 + 写 S: 盘）。
   - dashboard.service：在 0.0.0.0:8082 跑 dashboard/server.py（Flask）；并读取 .env 里的
     S_DRIVE_ROOT，使 /submit 录入能同步到 S: 盘队列。团队访问
     http://192.168.0.147:8082 看新闻汇总；页头「＋ 添加爬虫」→ /add 填表加新客户。
     注意：端口 8080 已被 nginx 占用（之前部署的 "AI-Report" 客户每周新闻情报看板，
     静态服务），故 Flask 改用 8082，不要改回 8080（会 Address already in use 启动失败）。
     提交后服务器把录入同步到 S: 盘队列（S_DRIVE_ROOT/_crawler_queue），由 WorkBuddy 侧的
     「火哥的绿龙虾」直接从局域网共享读取并接手写解析器、再 push 代码让服务器 pull 爬取。
     数据/录入不再经过 GitHub。
   - 依赖：requirements.txt 已含 flask>=3.0，install.sh 第 30 行已 pip 安装；无需额外操作。
   （频率 / 客户在 deploy/client-crawler.timer 的 OnCalendar 字段修改）
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
- **Ubuntu（hermes）**：每周一 09:00 跑 `run_weekly.sh` → 抓新闻 → `data/` + 写 S: 盘（`kb_export`）+ 生成看板 + 写 `status.json`（运行状态）。数据 / KB / 录入队列全部落 S: 盘，**不经过 GitHub**。GitHub 仅在脚本第一步 `git pull` 拉最新代码。
- **WorkBuddy（Notion MCP / AI）**：每周一 10:00 直接读取 S: 盘上的 `data/`（S_DRIVE_ROOT 局域网共享，WorkBuddy 侧可达），调用 Notion MCP 把新条目写入数据库 **客户每周新闻汇总**（ID `8c48dd185e224af4ac7237e98ae1a86e`），按 `source_url` 去重；并读取 S: 盘队列 `S_DRIVE_ROOT/_crawler_queue/queue.jsonl` 接手新录入。服务器不需要任何 Notion 密钥。
- **S: 盘归档 + KB 骨架**：每次爬取后 `kb_export` 把原始数据写 `S_DRIVE_ROOT/<client>/<category>/<date>.json`，并在 `S_DRIVE_ROOT/Obsidian/<client>/KB/` 生成 00-Index / 01-Facts / 02-Selling / 03-Compliance 骨架文件（idempotent，不覆盖已有内容）。AI 抽取事实/卖点填入 01/02 由 WorkBuddy 侧完成（option-3 分工），服务器不调 LLM。
- S_DRIVE_ROOT 通过 `.env`（gitignored）注入，client-crawler.service 与 dashboard.service 均用 `EnvironmentFile=-.../.env` 读取。
- **运行状态监控**：`run_weekly.sh` 末尾写 `status.json`（last_run / 各客户条数 / 0 条告警），8082 看板页头显示「上次运行时间 + 条数」，任一客户 0 条标红提醒；若配了 `WECOM_WEBHOOK` 还会推企业微信。

## 你（火哥）要确认
- hermes 跑完部署后，第一次 `run_weekly.sh` 能在 S: 盘生成 `sasol/news/<日期>.json` 与 `Obsidian/sasol/KB/` 四层文件（否则 WorkBuddy 收不到数据）。GitHub push 已不再需要（数据走 S: 盘）；仅需确认服务器 `git pull` 能拉到代码（若不通，代码更新改由 hermes rsync）。
- 看板（团队 LAN 访问）已含「添加爬虫」菜单（dashboard/server.py，Flask）；若 hermes 是早期按旧 prompt 部署、看板还是 `python -m http.server`，需重跑一次 install.sh 让 dashboard.service 改用 server.py 并装上 flask。
- 看板页头出现「上次运行 … ｜ 条数 …」即代表监控已生效；若显示空白说明 `run_weekly.sh` 尚未跑过（status.json 未生成）。
