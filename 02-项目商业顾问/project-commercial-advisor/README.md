# Project Commercial Advisor

一个通用的项目商业顾问插件。它在立项前形成可验证的商业判断，并在项目上线后使用真实经营结果检验和修正判断，帮助用户决定立项、继续、调整、追加投入、降低投入、暂停或停止。

## 边界

- 分析对象是项目作为一项商业投入，不是章节文本。
- 不评价小说段落是否好看，不承担编辑或改写。
- 不使用固定商业评分，也不把公开代理指标冒充订阅、收入或因果证据。
- 不运行定时任务、爬虫、数据库或自动登录。
- 平台规则和市场数据只在用户咨询时按需核验。

当前提供起点与 17K 的轻量平台入口、无预设题材的市场扫描协议，以及章节更新和利润模型的确定性计算器。平台规则与榜单只作为查询入口，每次咨询都需要重新核验。

17K 适配同时提供新书启动节点与测量参考，把现行官方条件、官方编辑经验和项目内部经营假设分开，用于规划申签、渠道、上架、更新库存和上线复盘；不会把单一项目的剧情或数据阈值固化成平台通则。

17K 市场扫描会先从当时实际可访问的男频榜单、分类、作品阶段和官方商业机制建立观察面，再归纳题材簇与市场机会。单次快照只支持当前热度观察，不被写成商业化趋势；公开排名、点击、收藏、推荐票和礼物不被当作订阅、留存或收入。

深度扫描可以进一步保存榜单快照、作品页与目录指标、首个公开正文章的聚合风格统计，并生成已执行的分析笔记本。目录条目与正文编号分开，阅读人次与订阅人数分开，公开支持者金额与作品收入分开；不保存整章正文或读者身份。

复现 17K 深度研究笔记本时，先安装 `scripts/requirements-notebook.txt`，再运行：

```powershell
python scripts/build_17k_deep_dive_notebook.py
```

## 仓库位置

Project Commercial Advisor 作为可独立验证的组件，维护在 [Ruwen Writing System](https://github.com/hunterhigh/ruwen-writing-system) 仓库的 `02-项目商业顾问/project-commercial-advisor/` 目录中。

它不依赖如文写作系统的运行代码，也不是第三个写作入口；与如文同仓维护是为了让公开项目结构和版本关系更清楚。

## 验证

```powershell
$env:PYTHONUTF8 = "1"
python -m unittest discover -s tests -p "test_*.py"
python /path/to/skill-creator/scripts/quick_validate.py ./skills/project-commercial-advisor
python /path/to/plugin-creator/scripts/validate_plugin.py .
```
