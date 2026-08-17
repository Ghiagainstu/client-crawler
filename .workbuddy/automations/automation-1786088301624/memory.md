# client-crawler → Notion 同步记录

## 2026-08-10 (首次运行)
- git pull: 已是最新 (Already up to date)
- 数据目录 data/sasol/ 含两个文件: 2026-08-06.json (含 /index.php/ 旧URL) 与 2026-08-07.json (规范化URL)
- 按 "latest run" 只处理 2026-08-07.json 的 3 条 (避免同批新闻用不同URL重复建页)
- 新建 Notion 页面: 3 条 (data_source_id 8a95ff01-...)
- 跳过: 0 条 (首次同步, seen-file 此前不存在)
- seen-file 初始化于 C:/Users/fireh/.cache/client-crawler/synced.json (写入 3 个 source_url)
- 注意: 2026-08-06.json 的 /index.php/ 形式 URL 未同步, 因其与 08-07 为同一批新闻的不同URL形态, 去重铁律下不重复建页

## 2026-08-17 (第二次运行)
- git pull: 已是最新 (Already up to date); 工作目录已在仓库内
- 数据格式变更: 本次 latest run 为 data/hitachi-hightech/site/2026-08-12.json —— 全站爬取 (298页), 非新闻 feed。字段仅有 url/title/meta_description/text/word_count/section, 无 published_at / media_source_url。
- 因 schema 与"新闻"语义不符 (缺发布日期/来源媒体), 先暂停并用 AskUserQuestion 与火哥确认 → 火哥选「仅同步新闻类板块」(events 39 + knowledge 76 = 115 页)。
- 新建 Notion 页面: 115 条 (data_source_id 8a95ff01-...), 分 8 批 (15×7 + 8) 创建; 其中 2 条由排查时的诊断占位页改写而成 (apmc2020, asm-microbe), 无残留 junk 页。
- 字段映射: 标题←title, 客户←"hitachi-hightech", 原文链接←url, 摘要←meta_description, 抓取时间←整站 crawled_at (2026-08-12T08:55:28); 发布日期/来源媒体留空 (数据无对应字段)。
- 关键技术坑: date:{属性}:is_datetime 必须传字符串 "1"/"0", 但 harness 会将其序列化为整数导致 API 报 "must be 0 or 1; wrote 1 instead of \"1\""。最终改为省略 is_datetime (日期值含时间分量, Notion 仍以 datetime 存储)。注意: 第 1 批曾以整数 1 成功, 属偶发, 不可依赖。
- 跳过 (已同步): 0 条 (hitachi 全为新); 累计 seen-file = 118 (115 hitachi + 3 sasol 历史), 全部唯一。
- 辅助脚本存于 .workbuddy/sync_prep.py (生成分批 payload; 该脚本不在 crawler/ 或 data/ 内, 未改动爬虫代码与数据 JSON)。
- 残留小瑕疵: batch6 第 2 条 content 正文的链接误写成 cm_data21.html (原文链接属性为正确 cm-data21.html), 仅正文可点击链接 404, 不影响去重与属性。

## 2026-08-17 (第三次运行 / 衍生改动)
- 本次非纯同步: 火哥就"爬虫数据/看板/调度"提了三个追问, 顺带落地了 8082 看板增强 + IP 迁移。
- 火哥三项决策: (1) **保留** Notion 新闻同步 + **同时**生成总结报告(总结报告走 8082 的 AI 报告通道, 由「绿龙虾全站 AI 分析」周一自动化产出, 非本自动化职责); (2) 给 8082 看板加「调度与运行状态」面板; (3) 服务器实际 IP 为 **192.168.0.220** (此前代码/手册写的是 .181)。
- 上周新增并已执行的客户端 = **hitachi-hightech** (git: 2a10cae add client, 0186951 site-mode crawl; 2026-08-12 全站爬 298 页)。注意: 本仓库 onboard/requests/ 与 queue.jsonl 均不存在 → 该接入非经 8082 /add 表单, 而是绿龙虾直接改代码提交; 提交队列现走 S: 盘(不在 git)。
- 8082 看板改动 (dashboard/build.py 模板 + 重新生成 index.html): header 下新增「调度与运行状态」区块, 展示 每月1日09:00 全量爬取 / 每月1日19:00 提交检查 + JS 动态算"下次运行" + 已接入客户 + 上次运行(来自 _status.json)。schedule 字典写死在 build.py main(), 须与 deploy/*.timer 保持一致。
- IP 迁移: dashboard/build.py, dashboard/index.html(再生), dashboard/manual.html, deploy/HERMES_PROMPT.md, README.md 中 192.168.0.181 全部改为 192.168.0.220 (含 SMB 共享路径)。顺手修正 manual.html 中 crawler-check.timer 旧文案(原误写"周一/三/五 19:00", 实为每月1日19:00)。
- 待确认: git commit + push 到 GitHub, 服务器 git pull 后才生效。push 属外部动作, 需火哥确认。
