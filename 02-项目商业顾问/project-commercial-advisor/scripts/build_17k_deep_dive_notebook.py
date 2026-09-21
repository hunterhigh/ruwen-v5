from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "17k" / "2026-08-31-deep-dive.ipynb"


def md(text: str):
    return nbf.v4.new_markdown_cell(text)


def code(text: str):
    return nbf.v4.new_code_cell(text)


cells = [
    md(
        """# 17K 男频深度市场研究：可复核分析笔记本

**决策问题：** 在不预设题材、不纳入内部能力的前提下，17K 男频当前公开市场事实支持哪些商业与竞品洞察？

**快照时间：** 2026-08-31（Asia/Taipei）  
**数据边界：** 只使用公开榜单、公开作品页、公开目录和首个公开正文章；不登录、不调用私有接口、不采集读者身份。订阅人数、作品实付金额、作者收入均未公开，保持未知。
"""
    ),
    code(
        """from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path.cwd()
if not (ROOT / 'research' / '17k' / 'data').exists():
    ROOT = ROOT.parent.parent
DATA = ROOT / 'research' / '17k' / 'data'

ranks = pd.read_csv(DATA / '2026-08-31-rank-snapshot.csv')
books = pd.read_csv(DATA / '2026-08-31-book-sample.csv')
style = pd.read_csv(DATA / '2026-08-31-style-sample.csv')

print({'rank_rows': len(ranks), 'book_rows': len(books), 'style_rows': len(style)})
"""
    ),
    md("## 1. 数据质量与口径检查"),
    code(
        """assert len(ranks) == 99
assert len(books) == 10
assert len(style) == 8
assert ranks.duplicated().sum() == 0
assert books['book_id'].duplicated().sum() == 0
assert style['book_id'].duplicated().sum() == 0
assert (books['read_times'] >= 0).all()
assert (books['word_count'] > 0).all()
assert style[['chars','paragraphs','sentences']].gt(0).all().all()

quality = pd.DataFrame({
    'dataset': ['rank_snapshot', 'book_sample', 'style_sample'],
    'rows': [len(ranks), len(books), len(style)],
    'duplicate_rows': [ranks.duplicated().sum(), books.duplicated().sum(), style.duplicated().sum()],
    'missing_book_id': [ranks['book_id'].isna().sum(), books['book_id'].isna().sum(), style['book_id'].isna().sum()],
})
quality
"""
    ),
    code(
        """surface_counts = ranks.groupby(['surface','period'], dropna=False).size().rename('rows').reset_index()
surface_counts
"""
    ),
    md(
        """**已知限制：** 榜单页只公开订阅名次，不公开订阅人数或销售额；作品页的“人次读过”是累计访问人次，不是独立读者；礼物区公开的元金额是特定支持者展示值，不是作品总收入或作者到手收入。"""
    ),
    md("## 2. 榜单交叉与异常集中"),
    code(
        """commercial_surfaces = ['male_subscription','male_new_subscription','male_recommendation','male_gift']
cross = (ranks[ranks['surface'].isin(commercial_surfaces)]
         .groupby('title')
         .agg(signal_surfaces=('surface','nunique'), best_rank=('rank','min'), surfaces=('surface', lambda s: ' / '.join(sorted(set(s)))))
         .sort_values(['signal_surfaces','best_rank'], ascending=[False,True]))
cross.head(15)
"""
    ),
    code(
        """clicks = ranks[ranks['surface'].eq('male_current_click')].copy()
clicks['displayed_value'] = pd.to_numeric(clicks['displayed_value'])
click_top1_share = clicks.iloc[0]['displayed_value'] / clicks['displayed_value'].sum()
click_top1_to_2 = clicks.iloc[0]['displayed_value'] / clicks.iloc[1]['displayed_value']
pd.Series({
    'top1_title': clicks.iloc[0]['title'],
    'top1_displayed_clicks': int(clicks.iloc[0]['displayed_value']),
    'top1_share_of_top30': round(click_top1_share, 4),
    'top1_to_top2_ratio': round(click_top1_to_2, 2),
})
"""
    ),
    md("## 3. 作品规模、章节与公开商业标记"),
    code(
        """books['avg_words_per_latest_numbered_chapter'] = (books['word_count'] / books['latest_numbered_chapter']).round(0)
book_view = books[[
    'title','read_times','word_count','directory_entries','latest_numbered_chapter',
    'avg_words_per_latest_numbered_chapter','weekly_gifts','weekly_gift_rank',
    'top_supporter_display_yuan','subscription_week_rank','new_subscription_week_rank',
    'recommendation_week_rank','gift_week_rank','current_click_rank'
]].sort_values('read_times', ascending=False)
book_view
"""
    ),
    code(
        """book_summary = pd.Series({
    'read_times_min': int(books['read_times'].min()),
    'read_times_median': int(books['read_times'].median()),
    'read_times_max': int(books['read_times'].max()),
    'word_count_min': int(books['word_count'].min()),
    'word_count_median': int(books['word_count'].median()),
    'word_count_max': int(books['word_count'].max()),
    'latest_chapter_min': int(books['latest_numbered_chapter'].min()),
    'latest_chapter_max': int(books['latest_numbered_chapter'].max()),
})
book_summary
"""
    ),
    md(
        """不能从上表推导订阅转化率：榜单池、阅读人次的累计窗口、作品年龄和流量入口不同。特别是《乾坤一主》新书订阅周榜第 1，但公开阅读人次只有 2,534；这个反差证明“第 1 名”是池内相对位置，不是绝对销量。"""
    ),
    md("## 4. 首章文字风格统计"),
    code(
        """def style_cluster(row):
    if row['avg_paragraph_chars'] >= 55:
        return '长章长段/章回叙事'
    if row['dialogue_char_share'] < 0.20:
        return '场景动作主导'
    if row['short_paragraph_share'] >= 0.60:
        return '碎段快切/强移动端节奏'
    if row['dialogue_char_share'] >= 0.37:
        return '高对话推进'
    return '均衡叙事/对话并进'

style['style_cluster'] = style.apply(style_cluster, axis=1)
style_view = style[[
    'title','chars','avg_sentence_chars','avg_paragraph_chars','short_paragraph_share',
    'dialogue_char_share','questions_per_1k','exclaims_per_1k','style_cluster'
]].sort_values('dialogue_char_share', ascending=False)
style_view
"""
    ),
    code(
        """style_summary = style[[
    'chars','avg_sentence_chars','avg_paragraph_chars','short_paragraph_share',
    'dialogue_char_share','questions_per_1k','exclaims_per_1k'
]].agg(['min','median','max']).round(3)
style_summary
"""
    ),
    md(
        """风格统计只代表首个公开正文章，适合观察开篇包装，不代表全书平均风格。8 本样本分散在至少四类：碎段快切、场景动作主导、高对话推进、长章长段。不存在一个可诚实概括全部头部的“17K 爆款文风”。"""
    ),
    md("## 5. 经验证的洞察边界"),
    code(
        """visibility = pd.DataFrame([
    ['订阅榜名次','公开','可用于池内相对位置','不可换算订阅人数或收入'],
    ['订阅人数','不公开','未知','需作者后台或平台授权数据'],
    ['作品实付金额/作者收入','不公开','未知','礼物展示金额不能替代'],
    ['累计阅读人次','公开','历史曝光与生命周期代理','不是独立读者'],
    ['礼物周榜/周礼物数','公开','短期支持强度代理','不等于总流水'],
    ['单个支持者展示金额','公开','头部支持者强度案例','不等于作品总收入或作者到手'],
    ['字数/目录/最新编号','公开','供给规模与连载形态','目录含公告，需去杂项'],
    ['首章文本统计','公开抽样','开篇节奏与表达形态','不代表全书平均'],
], columns=['metric','availability','valid_use','invalid_inference'])
visibility
"""
    ),
    md(
        """## 6. 结论

1. 17K 男频当前不是单一题材市场，而是至少三种商业信号并存：成熟长线订阅、新书小池相对领先、小圈层高强度礼物。
2. 总订阅头部的规模跨度极大；新书订阅榜第 1 也可能只有数千公开阅读人次，因此必须先分榜单池，再谈竞争。
3. 礼物信号存在“低覆盖、高强度”特征。《一口粮》公开阅读人次不高，却进入礼物周榜第 2；这更接近核心读者浓度，而不是大众规模。
4. 文风没有统一模板。商业信号强的作品既有 70% 以上短段的移动端快切，也有 7,000 字首章、长段章回式叙事；题材与表达必须基于具体目标市场事实继续验证。
5. 订阅人数与付费金额仍不可见。任何给出作品订阅数、订阅收入或转化率的数字，除非来自作者后台或平台授权数据，都是伪精确。
"""
    ),
]

nb = nbf.v4.new_notebook(cells=cells)
nb["metadata"]["kernelspec"] = {
    "display_name": "Python 3",
    "language": "python",
    "name": "python3",
}
nb["metadata"]["language_info"] = {"name": "python", "version": "3"}

OUT.parent.mkdir(parents=True, exist_ok=True)
nbf.write(nb, OUT)

client = NotebookClient(nb, timeout=120, kernel_name="python3")
client.execute(cwd=str(ROOT))
nbf.write(nb, OUT)
print(OUT)
