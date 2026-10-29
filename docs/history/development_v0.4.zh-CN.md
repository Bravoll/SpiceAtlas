# v0.4 开发与验收说明

日期：2026-10-28。

保留植物图谱视觉，把语言策略、服务状态、图片词库、清洗审核和可独立复制的本地版本接到同一阅读流程。

## 实现边界

- `atlas/catalogue.py`：SQLite 目录、层级图、简繁规范化的名称／别名检索、FTS5、有界近似拼写、审核档案。查询按页返回，不加载全库到浏览器。
- `atlas/curation.py` 与 `data/research_curation/`：实体类型准入、有限人工例外、清洗决策与证据索引。未知记录进入待审核；植物分类身份不证明可食用。
- `atlas/resources.py`：界面模式和内容语言独立；仅 Auto + Hans 使用国内优先，手动 Hans 使用国际优先。
- `atlas/health.py`：启动后台检测、600 秒全部服务重测、浏览器／后台双路径、临时可用性与持久通知。HTTP 可用与 iframe 限制分开。
- `atlas/image_lexicon.py`：每版本的图片形态库，由真实文件名采样的种子初始化，支持独立的包装等图片筛选；不改知识记录。
- `atlas/providers.py`：实时 Wiki API、正文清理／链接修复、浏览器回传的同样清理、Commons 元数据、形态排名、翻译缓存。
- `atlas/translations.py`：本地兼容聊天 API、Google Cloud Translation v2、Azure Translator v3。链接标记和数字经过完整性核对，最多 8 段。
- `atlas/workspaces.py`：版本登记在外、每版本数据库在内；SQLite backup API 复制，工作上下文用 ContextVar 固定；复制／切换前暂停导入。单进程使用。
- `atlas/activity.py`：带时间戳的日志、收藏、历史、通知及其排序。
- 前端：固定视口双栏、对齐页首控件、三种手动语言、自动图片、来源分语言、状态改变后延迟全局刷新、恢复当前状态并执行触发操作。

从旧版迁入配置只在首次初始化执行。版本配置中的密钥只写，不通过 GET 返回；日志不记录密钥。发行包排除版本目录、个人配置、正文缓存和照片。

## 数据与证据

原始输入 19,078 条：1,239 条维基分类候选加 17,839 条 GBIF 记录。最终 18,379 条（92 材料候选、18,287 植物参考），699 条原记录归档（392 排除、101 待审核、206 合并）。

清洗检查 1,222 个唯一 Wikidata 实体、175 个实体类型，并抽查初始待定条目的维基简介。Wikidata 原始结构化证据保留为 CC0 数据；发行包不附这些维基简介正文，只附来源索引、时间和清洗理由。13 个原展签的具体名称、形态与范围提示保留。

复核时应同时查看 `cleaning_report.json`、`cleaning_decisions.json`、`entity_type_rules.json`、`asset_validation.json` 和数据库 quarantine。单纯的类型规则是保守准入，不是整个香料领域的真值分类器。

原始 v0.3 输入是清洗脚本的前提；发行包中的 baseline 已清洗。研究脚本用于有对应原始输入的复现，不能把已清洗 baseline 当成原始 v0.3 再运行并比较原始计数。日常增量更新走应用的导入流程。

图片库：30 个原料、39 次 Commons `namespace 6 + filetype:bitmap` 查询、326 个返回文件名、12 类形态。所有查询参数、获取时间和真实空结果保存；预设语义词与实际观察词频分开。

## 检查方式

```bash
uv run python -m unittest discover -s tests -q
node --check static/app.js
```

行为 DOM 测试需要 LinkeDOM；外部安装后设置 `SPICE_LINKEDOM_PATH` 指向模块，再运行 `node tests/ui_acceptance.cjs`。测试使用 `tests/fixture_service.cjs` 的合成 API。

真实外部来源检查是显式可选的 `uv run python tests/live_smoke.py`，不调用用户配置的云端翻译或模型；结果写入 `data/verification_v04_live.json`。此脚本会产生本机运行缓存和连接通知，不属于纯离线单元测试。

可选 UI 预览使用 `node tests/preview_fixture.mjs --port 4173`。它是合成资料服务器，不是生产 Python 后台，页面有明显标记。生产通过 `launch.py` 运行。

后端 87 项和 DOM 行为 15 项检查通过。最终测试计数与真实浏览器测量见 `data/verification_v04.json`。桌面浏览器验收 1363 × 936 视口，外层 body clientHeight 与 scrollHeight 均为 936；目录／正文高度均为 833，各自 overflow auto；两栏分别滚动到 936 时外层仍为 0。页首六个控件中心均为 y=50.9375。检查了繁体界面、翻译设置和版本管理。

## 已知限制

- 未接入用户实际 LM Studio，也未用个人 Google / Azure 凭据做实际翻译；适配器请求结构、密钥隐藏、排除规则、链接与数字校验由模拟测试覆盖。
- 网络可用性依运行位置与时间变化。一次 HTTP 错误不是永久服务结论；页面会继续定时检测。
- 部分来源只支持跳转。iframe 仅在源站允许时尝试；不移除原站限制。
- 自动图片仍是候选；标题与描述筛选不能替代人工鉴定。
- 版本是可编辑工作空间，需要冻结状态时主动复制；非多进程／多用户并发数据库系统。
- 视觉验收覆盖桌面。窄屏有响应式规则，本次没有额外移动设备实测。
- 当前源码同步至 `Bravoll/spice-atlas-local` 私有仓库。GitHub 自动更新、完整项目作者与开源许可声明保持后续范围。
- Git 源码中的数据库使用校验过的 gzip 种子保存，首次启动自动恢复；保留已存在的本地数据。额外的种子恢复测试覆盖成功恢复、校验失败、大小限制和版本初始化。
