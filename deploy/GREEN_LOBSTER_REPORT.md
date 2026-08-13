# 绿龙虾 · 全站结构 AI 分析报告模板

本模板定义「全站结构（site 模式）」爬取完成后，绿龙虾应产出的 AI 分析报告结构。
报告目标读者：火哥（Paid Media / SEM 策略），用于理解客户站点、支撑投放决策。

每次分析都按下面 **三根支柱** 组织，不要堆砌全文摘要，要带着「这对中国市场 SEM 有什么用」的视角去提炼。

---

## 数据源
- `<S_DRIVE_ROOT>/<client>/site/<date>.json`：完整按板块分组的全文
  - 结构：`{client, base_url, crawled_at, total_pages, sections:{板块:[{url,title,meta_description,text,word_count,section}]}}`
- `<date>_index.json`：板块大纲（板块 → 页数 + 页面清单）
- `<date>_index.md`：人读大纲

## 产出
- `<S_DRIVE_ROOT>/<client>/site/<date>_ai_report.html`（自包含、内联 CSS、可直接浏览器打开）
- `<date>_ai_report.md`（便于 Obsidian 阅读）
- 同步更新 `<S_DRIVE_ROOT>/Obsidian/<client>/KB/` 下四个 KB 文件（00-Index / 01-Facts / 02-Selling-Points / 03-Compliance），**追加带日期小节，不覆盖 approved 段落**

---

## 报告骨架（必须按此三支柱，顺序固定）

### 一、公司介绍（Company Introduction）
从全站正文提炼，而不是泛泛而谈：
- 公司定位与一句话价值主张（用官网原话支撑）
- 业务板块架构（对应 sections 里的 company / knowledge / be_bold 等，说明各板块讲什么）
- 关键事实与数字：营收、员工、专利、全球据点、成立年份等（one fact = one source，附 URL）
- 全球网络 / 在中国或目标市场的存在（如有）
- 品牌叙事主线（如 be_bold 这类 slogan 的含义与落点）

### 二、网站产品（Website Products）
按产品线 / 解决方案梳理，而非罗列页面：
- 核心产品 / 服务矩阵（semiconductor、medical、electronic materials、science 等，提炼每条线的定位与典型产品名）
- 各产品线的目标客户与典型应用场景
- 官网强调的差异化卖点 / 技术优势（每条链接事实层来源）
- 内容深度判断：哪些产品线官网讲得细（可作落地页参考）、哪些偏弱（内容缺口 = 投放时的补充素材机会）

### 三、对 Paid Search 的作用与意义（Implications for Paid Search）
这是报告的核心交付，从 SEM 策略视角给可执行建议：
- **关键词机会**：从产品名 / 技术术语 / 应用场景反推可投的中文 & 英文搜索词（品牌词 + 通用词 + 长尾），标注高意图词
- **竞品对标**：官网提及的竞争对手或替代方案，对应可做的竞品拦截词
- **落地页映射**：把投放词对应到官网现有页面（URL），指出哪些词缺官方落地页（需自建 LP 或引导到概览页）
- **受众与投放建议**：每条主力产品线适合投百度 / Google Ads 的受众画像、匹配类型、预算优先级建议
- **合规与风险**：医疗 / 认证 / 地域限制等需注意的宣称红线（链接 03-Compliance），避免广告违规

---

## 风格约束
- 结论先行，每节给「要点」再给证据
- 事实必须带来源 URL（可点击）
- 不编造官网没有的产品 / 数字
- 中文输出，专业、克制、可执行
- 末尾给「火哥下一步可执行清单」（3-5 条）
