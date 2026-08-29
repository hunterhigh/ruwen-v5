# 网文体裁编辑器

一个与 Ruwen 独立的轻量 Codex 插件，用于直接编辑 Author 已完成但尚未批准的中文网文初稿。

它可以进行章节补充、叙事扩写、解释性讲述、拼接重织、文学平衡和中文表达整理。修改后的正文仍是候选稿；编辑器不加入 Author 工作流，不写正典，也不更新项目记忆。

## 使用边界

```text
Author 批准前初稿
→ 用户单独调用网文体裁编辑器
→ 编辑器保留原稿并直接修改候选稿
→ 原项目继续审阅与核验
→ 用户批准后由原项目写入正典
```

- 只编辑已经存在的正文，不代替 Author 从大纲写第一稿；
- 可以深度补写，但不能擅自改变锁定剧情、人物选择和世界规则；
- 没有实际阅读收益时允许不改；
- 不依赖 Ruwen 的目录或运行代码，可独立复制和安装。

## 结构

- `skills/web-fiction-genre-editor/SKILL.md`：唯一技能入口；
- `references/editing-method.md`：网文深度编辑与重织方法；
- `references/context-and-approval.md`：读取范围、修改权和批准边界；
- `validation/`：跨场景行为验证。

## 验证

在本插件根目录运行：

```powershell
python C:\Users\admin\.codex\skills\.system\skill-creator\scripts\quick_validate.py .\skills\web-fiction-genre-editor
python C:\Users\admin\.codex\skills\.system\plugin-creator\scripts\validate_plugin.py .
```
