# StockWidget 发版与上传流程规范

> 本文档是项目发版的唯一标准流程，后续所有版本发布按此执行。
> 建立日期：2026-08-19（v1.0.1 发版时）

## 一、版本机制说明

| 项目 | 位置 | 说明 |
|---|---|---|
| 程序内部版本号 | `VersionCheck.py` → `APP_VERSION` | 打进 exe 里，程序自报版本用 |
| 远端版本文件 | 仓库 `main` 分支根目录 `Version` 文件 | 单行内容如 `v1.0.1`，客户端靠它检测更新 |
| Release 标签 | GitHub Release 的 tag（如 `v1.0.1`） | 必须与远端 Version 文件内容一致 |
| Release 附件 | `StockWidget.exe` | 固定文件名，客户端按固定 URL 下载 |

**更新检测原理**：客户端启动后读取 `https://raw.githubusercontent.com/userSywang/StockWidget/main/Version`（raw 文件直链，不走 GitHub API，无 60 次/小时限流问题），发现远端版本高于本地 `APP_VERSION` 时提示更新，从 `https://github.com/userSywang/StockWidget/releases/download/{tag}/StockWidget.exe` 后台下载并自动替换重启。

**三条铁律**：
1. `APP_VERSION`、`main` 分支 `Version` 文件、Release tag **三者必须一致**，否则用户更新完会反复弹更新提示（v1.0.1 曾因此返工）。
2. 附件文件名固定为 `StockWidget.exe`，不可带版本号后缀。
3. 必须先有 tag 对应的 Release 存在，才能上传附件。

## 二、发版步骤（五步）

### 第 1 步：升级内部版本号

编辑 `VersionCheck.py`：

```python
APP_VERSION = "1.0.2"   # 改成新版本
```

### 第 2 步：重新打包

```powershell
cd "F:\360MoveData\Users\Administrator\Desktop\StockWidget"
& ".\.venv\Scripts\python.exe" -m PyInstaller StockWidget.spec --noconfirm --distpath dist --workpath build
```

产物：`dist\StockWidget.exe`（单文件模式，约 60MB，耗时 2~5 分钟）。

打包后**务必核对时间戳**，确认 exe 是刚生成的：

```powershell
Get-Item ".\dist\StockWidget.exe" | Select-Object Length, LastWriteTime
```

**exe 版本信息嵌入（自动）**：`StockWidget.spec` 打包时读取 `VersionCheck.py` 的 `APP_VERSION`，自动生成 `build\version_info.txt` 嵌入 exe 属性（文件右键 → 详细信息可见 FileVersion / ProductVersion），无需手工维护版本文件。打包后核对：

```powershell
(Get-Item ".\dist\StockWidget.exe").VersionInfo.FileVersion   # 应输出与 APP_VERSION 一致
```

若显示 `0.0.0` 或旧版本号，说明打包前忘了执行第 1 步升版本，需重打。

### 第 3 步：更新仓库 Version 文件并推送 main

```powershell
# 将仓库根目录的 Version 文件内容改为 v1.0.2（单行、无多余字符、无 BOM）
git add Version VersionCheck.py
git commit -m "release: v1.0.2"
git push origin main    # 当前工作分支若不是 main，先合并到 main 再推
```

验证远端生效（返回内容应为 `v1.0.2`）：

```powershell
curl.exe -s "https://raw.githubusercontent.com/userSywang/StockWidget/main/Version"
```

### 第 4 步：创建 Release 并上传附件

```powershell
# 4a. 若该 tag 的 Release 不存在，先创建（标题即版本号）
gh release create v1.0.2 --title "v1.0.2" --notes "更新说明写这里" -R userSywang/StockWidget

# 4b. 上传 exe 附件（已存在同名附件时加 --clobber 覆盖）
gh release upload v1.0.2 ".\dist\StockWidget.exe" --clobber -R userSywang/StockWidget
```

仅替换旧版本的附件（如 v1.0.1 这次的情况，tag 不变只换文件）：

```powershell
gh release upload v1.0.1 ".\dist\StockWidget.exe" --clobber -R userSywang/StockWidget
```

### 第 5 步：验证

```powershell
# 查看附件信息（核对 size 与 dist 本地文件一致）
gh release view v1.0.2 -R userSywang/StockWidget --json assets,tagName
```

再用旧版本客户端实测一轮完整链路：启动 → 提示新版本 → 后台下载 → 重启后不再弹更新提示。

## 三、本机 gh 工具环境（特殊说明）

本机 gh 为**便携版**，且因沙箱限制不能写配置文件，使用时需通过环境变量传令牌：

```powershell
$env:GH_TOKEN = "<GitHub Personal Access Token>"   # scope: repo
& "F:\Tools\gh\bin\gh.exe" <命令>
```

- gh 程序位置：`F:\Tools\gh\bin\gh.exe`（已加入用户 PATH，新开窗口可直接用 `gh`）
- 令牌获取：https://github.com/settings/tokens/new → 勾选 `repo` → 生成
- 令牌失效（报 401）时重新生成一个即可，可在 https://github.com/settings/tokens 随时撤销管理
- 备用方案（无 gh 时）：网页端手动上传，Release 页面 → Edit → 拖入 exe

## 四、代码列表每日自动更新（全自动，无需人工干预）

股票代码索引 `resources/stock_codes_list.json` 由 GitHub Actions 工作流 `.github/workflows/update-codes.yml` 自动维护：

- **触发时间**：每个交易日（周一至周五）北京时间 15:30 收盘后自动运行；也可在仓库 Actions 页面手动触发。
- **流程**：用 baostock 拉取最新证券列表 → 执行 `tools/build_stock_code_index.py` 重新生成索引 → 内容有变化才自动提交推送 main，无变化则跳过。
- **客户端配合**：程序启动优先加载本地缓存 `%APPDATA%\StockWidget\stock_codes_list.json`；启动约 5 秒后后台线程从 main 分支 raw 地址拉取最新索引覆盖缓存（当天已刷新过则跳过），断网或失败时静默回退，不影响使用。
- **优先级**：本地下载缓存 > 打包时内置的静态索引，保证老版本 exe 也能搜到新上市的股票。
- **排查**：仓库 Actions → "Update Stock Code Index" 看运行记录；本地缓存损坏时删除该文件重启程序即可自动重建。

> 该工作流独立于发版流程，直接推送 main 的索引文件。发版打包前建议确认其无连续失败记录，避免内置了过期索引。

## 五、常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| 更新后每次启动都弹"发现新版本" | exe 内 APP_VERSION 低于远端 Version | 按"三条铁律"核对一致性，重新打包上传 |
| 更新重启后报 "Failed to load Python DLL" | 更新脚本继承了旧进程的 PyInstaller 环境变量 | 已在 v1.0.1 修复（脚本内清 `_MEIPASS2` 等变量），若复现检查 `build_updater_script` |
| 下载附件报 404 | 该 tag 的 Release 未上传附件 | 执行第 4b 步 |
| 检查更新失败 | raw.githubusercontent.com 缓存未刷新 | 等 1~5 分钟重试，或确认 Version 已推送到 main |
| 想在测试分支验证更新 | 默认只看 main | 设环境变量 `STOCKWIDGET_UPDATE_BRANCH=codex/strategy-alerts-page` |

## 六、发布前检查清单

- [ ] `APP_VERSION` 已升级，与目标 tag 一致
- [ ] `dist\StockWidget.exe` 时间戳为最新打包时间
- [ ] exe 属性 `FileVersion` 与 `APP_VERSION` 一致（`version_info.txt` 自动生成）
- [ ] `Version` 文件内容 = `v<新版本>`，已推送 main
- [ ] Release tag 已创建，附件 `StockWidget.exe` 已上传
- [ ] 旧客户端实测：能检测、能下载、重启后不再提示更新
