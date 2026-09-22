# 创作加载索引

## 设计世界与历史

依次读取：

1. `world/00-canon-rules.md`
2. `world/01-approved-foundations.md`
3. `story-bible.md`
4. `proposals/01-geography-and-political-map-v0.1.md`
5. `proposals/02-seventy-year-history-and-thirty-powers-v0.1.md`
6. `proposals/02a-historical-event-catalog-v0.1.md`

提案内容未经批准不得倒灌正典。

## 设计人物

依次读取：

1. `world/01-approved-foundations.md`
2. `proposals/04-opening-era-ensemble-v0.1.md`
3. `continuity-ledger.md`
4. 对应人物档案

## 设计战争

依次读取：

1. `proposals/01-geography-and-political-map-v0.1.md`
2. `proposals/03-samurai-armies-and-visual-system-v0.1.md`
3. `author-voice/scene-modes/战场与本阵.md`
4. `validation-rules.md`

## 写正文

1. 路由阶段可读取正典、计划、连续性与人物档案，只选择会改变当前人物知觉、选择、身体、关系或可用行动的事实。
2. 由 `situation-seeds/` 中的当前情境、`author-voice/project-core.md`、一个 POV 镜头、至多一个场景模式、少量激活事实和一条当前指令编译 `.work/` 中的临时作者包。
3. 正文阶段只使用编译后的作者包，不直接浏览完整正典、连续性、提案、校验规则或旧版纠错历史。
4. 候选正文写入 `drafts/`；依用户要求不调用子 Agent，各创作角色在当前任务中顺序执行，并承认上下文隔离降低。
5. 完稿后再读取 `validation-rules.md` 做硬性审查。草稿获用户明确批准前，不更新正式连续性，也不作为下一章既定事实。

## 赣南开局分章入口

- 第一章（赤身求生与战场所得）：`situation-seeds/chapter-001-seed.md`
- 第二章（山庙哑客）：`situation-seeds/chapter-002-seed.md`

情境种子是写作边界，不是已经发生的正文。后一章只能继承前一章获批准正文中实际发生的细节。
