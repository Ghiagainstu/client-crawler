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
   - client-crawler.timer：每周一 09:00 跑 deploy/run_weekly.sh（爬新闻 + 生成看板 + 推 GitHub）
   - dashboard.service：在 0.0.0.0:8082 跑 dashboard/server.py（Flask）。团队访问
     http://192.168.0.147:8082 看新闻汇总；页头「＋ 添加爬虫」→ /add 填表加新客户。
     注意：端口 8080 已被 nginx 占用（之前部署的 "AI-Report" 客户每周新闻情报看板，
     静态服务），故 Flask 改用 8082，不要改回 8080（会 Address already in use 启动失败）。
     提交后服务器把录入推回 GitHub，由 WorkBuddy 侧的「火哥的绿龙虾」接手写解析器并爬取。
   - 依赖：requirements.txt 已含 flask>=3.0，install.sh 第 30 行已 pip 安装；无需额外操作。
   （频率 / 客户在 deploy/client-crawler.timer 的 OnCalendar 字段修改）
5. 确保本机对 github.com 有 push 凭证（deploy key 或用户凭证），
   因为 run_weekly.sh 抓完会把 data/ 推回 GitHub，供 WorkBuddy 同步 Notion。
6. 汇报：部署结果、冒烟测试条数、下次运行时间。

注意：
- Notion 同步由另一侧的 WorkBuddy（已连 Notion MCP）负责，你无需处理 token 或 MCP。
- 后续 HTML 看板也承载在这台机上，团队通过局域网访问。
约束：遵守 robots.txt，代码内已限速（article_delay=1s），不泄露任何密钥。
```

---

## 架构说明（给你参考）
- **Ubuntu（hermes）**：每周一 09:00 跑 `run_weekly.sh` → 抓 Sasol 新闻 → `data/` 推回 GitHub。
- **WorkBuddy（Notion MCP）**：每周一 10:00 拉取 GitHub 上的 `data/`，调用 Notion MCP 把新条目写入
  数据库 **客户每周新闻汇总**（ID `8c48dd185e224af4ac7237e98ae1a86e`），按 `source_url` 去重。
- 服务器不需要任何 Notion 密钥。
- **S: 盘归档 + KB 骨架**：每次爬取后 `kb_export` 把原始数据写 `S_DRIVE_ROOT/<client>/<category>/<date>.json`，
  并在 `S_DRIVE_ROOT/Obsidian/<client>/KB/` 生成 00-Index / 01-Facts / 02-Selling / 03-Compliance 骨架文件
  （idempotent，不覆盖已有内容）。AI 抽取事实/卖点填入 01/02 由 WorkBuddy 侧完成（option-3 分工），服务器不调 LLM。
- S_DRIVE_ROOT 通过 `.env`（gitignored）注入，client-crawler.service 用 `EnvironmentFile=-.../.env` 读取。

## 你（火哥）要确认
- hermes 跑完部署后，第一次 `run_weekly.sh` 能成功 `git push`（否则 WorkBuddy 收不到数据）。
- 看板（团队 LAN 访问）已含「添加爬虫」菜单（dashboard/server.py，Flask）；若 hermes 是早期按旧 prompt 部署、
  看板还是 `python -m http.server`，需重跑一次 install.sh 让 dashboard.service 改用 server.py 并装上 flask。
