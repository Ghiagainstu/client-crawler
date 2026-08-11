# client-crawler → Notion 同步记录

## 2026-08-10 (首次运行)
- git pull: 已是最新 (Already up to date)
- 数据目录 data/sasol/ 含两个文件: 2026-08-06.json (含 /index.php/ 旧URL) 与 2026-08-07.json (规范化URL)
- 按 "latest run" 只处理 2026-08-07.json 的 3 条 (避免同批新闻用不同URL重复建页)
- 新建 Notion 页面: 3 条 (data_source_id 8a95ff01-...)
- 跳过: 0 条 (首次同步, seen-file 此前不存在)
- seen-file 初始化于 C:/Users/fireh/.cache/client-crawler/synced.json (写入 3 个 source_url)
- 注意: 2026-08-06.json 的 /index.php/ 形式 URL 未同步, 因其与 08-07 为同一批新闻的不同URL形态, 去重铁律下不重复建页
