# 17K 男频平台适配实施计划

日期：2026-08-31
设计依据：`docs/superpowers/specs/2026-08-31-17k-platform-adapter-design.md`

## 目标

在不改变现有起点适配与商业计算行为的前提下，为项目商业顾问增加 17K 平台资料和无预设题材市场扫描能力。第一轮扫描只使用 17K 男频外部市场事实，不以作者或项目内部条件筛选样本。

## 任务一：用失败测试固定新增契约

修改 `tests/test_package_structure.py`：

- 要求 manifest 版本为 `0.2.0`；
- 要求 `SKILL.md` 引用 `references/platforms/17k.md`、`references/market-selection.md` 和 `assets/market-scan-template.md`；
- 要求新增文件存在且不包含占位符；
- 检查 17K 资料具有查询时核验、官方入口、访问边界和代理指标限制；
- 检查市场扫描先观察后归纳、单次快照不等于趋势、内部因素隔离和缺失值规则；
- 检查模板具有来源时间、样本条件、证据分类和限制字段。

运行包结构测试并确认失败来自尚未实现的新增契约，而不是旧功能回归。

## 任务二：核验 17K 当前官方入口

只使用当前公开可访问页面或搜索结果定位：

- 17K 首页、男频入口、榜单、分类和作品页；
- 作者平台、帮助、福利、签约、VIP、推荐、活动或版权相关官方入口；
- 页面实际显示的公开字段、周期和作品阶段；
- 登录、动态页面或访问限制。

记录核验日期。无法确认的规则不写成确定事实；第三方页面不替代现行官方规则。

## 任务三：实现平台资料与市场扫描协议

新增：

- `skills/project-commercial-advisor/references/platforms/17k.md`；
- `skills/project-commercial-advisor/references/market-selection.md`；
- `skills/project-commercial-advisor/assets/market-scan-template.md`。

平台资料保存入口、可观察字段、查询时检查和误判边界，不保存当前热门结论。市场扫描协议规定观察面、去重、阶段分层、事后归纳、证据分类及当前热门/商业机制/趋势的不同门槛。模板只保存复核所需的最小证据。

## 任务四：接入技能与插件说明

修改：

- `skills/project-commercial-advisor/SKILL.md`：增加 17K 和无预设市场扫描按需路由；
- `README.md`：说明 17K 能力及其边界；
- `.codex-plugin/plugin.json`：版本提升到 `0.2.0`，界面描述增加市场扫描能力但不夸大商业效果；
- `validation/behavior-protocol.md`：增加 17K 无预设选题案例；
- `validation/behavior-results.md`：记录实际完成的静态和自动化验证，保留尚未完成的前向验证状态。

## 任务五：验证与提交

运行：

1. `python -m unittest discover -s tests -p "test_*.py"`；
2. skill 结构校验；
3. plugin manifest 校验；
4. `git diff --check`；
5. 检查未修改工作区其他一级仓库或 Ruwen 写作本体。

失败时只修复与本次适配相关的问题。全部通过后提交实现变更，再在新的研究阶段使用该能力。

## 任务六：首次 17K 市场扫描

按新协议开展一次查询时研究：

- 先记录当前官方页面、观察时间、榜单周期和可访问限制；
- 从实际男频市场表面建立样本，不预设题材；
- 采集后归纳题材簇、需求承诺、作品形态和商业信号；
- 分开报告当前热门、平台商业机制和有跨期证据支持的趋势；
- 明确不足以判断的订阅、留存、收入与因果关系；
- 将首次研究作为行为验证材料，由用户阅读验收。
