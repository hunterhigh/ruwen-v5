# Ruwen 项目阅读器

本地、只读的 Ruwen 项目阅读与批注批次工具。项目文件始终是唯一正典；阅读器只写项目内的 `.ruwen/control.sqlite3` 和封存快照 `治理/批注/批次-NNNN.json`。

## 运行

需要 Python 3.11 或更高版本。

```powershell
python -m pip install .
ruwen-reader --project "C:\path\to\Ruwen项目"
```

也可以运行：

```powershell
python -m ruwen_project_reader --project "C:\path\to\Ruwen项目"
```

服务只绑定本机回环地址，并为每次启动生成随机访问令牌。界面与字体均保存在本地，不需要网络连接。

每个项目分别保存自己的批注、批次、最近阅读文件和项目名字体。关闭服务或重启电脑不会清除这些状态；再次打开同一项目即可继续。

若正在开发阅读器本身，可用 `python -m pip install -e .` 安装可编辑版本。

## 数据

- 草稿、批注与批次状态：`.ruwen/control.sqlite3`
- 封存快照：`治理/批注/批次-NNNN.json`

封存快照不会重复出现在左侧文档树中；可从批次抽屉查看既往批次与快照位置。

备份项目目录即可同时备份正典和阅读器治理数据。卸载阅读器不会删除项目数据；若需要完全移除运行状态，可在确认备份后手动删除项目的 `.ruwen/`。

## 安全边界

- 项目正文只读。
- 拒绝项目外路径、符号链接逃逸和超限文件。
- 不自动上传文件，不调用 AI，不自动修改正典。
- 批次封存后不可编辑；修正进入下一批。

## 测试

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -p "test_*.py"
```
