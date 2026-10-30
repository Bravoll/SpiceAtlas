# v0.6 开发与验收说明

日期：2026-10-29（澳大利亚东部夏令时间）。本地候选，等待用户检验；未 commit、未 push、未部署。仓库已由用户改为公开，此变化不等于应用已上线托管。

本版基于 0.5 的未提交工作继续修改。上一版完整开发说明保存在 `docs/history/development_v0.5.zh-CN.md`，历史测试与日期不改名冒充当前结果。对外 README 已按可直接随提交使用的产品说明整理，验收流程留在本文件与验证记录。

## 实施范围

### Windows 后台启动

`run.cmd` 只负责定位 pythonw / pyw 并启动 `Start_Atlas.pyw`，随后退出。`desktop/gui.py` 使用标准库 Tk 显示真实阶段：5 环境、15 准备、30 依赖、70 校验、80 目录、88 服务、90 等待就绪、97 浏览器、100 完成。耗时阶段显示忙碌状态；百分比不是下载量或秒数预测。无需管理员权限，不设置开机启动，不更改 PowerShell 执行策略。

`desktop/core.py` 优先 `uv sync --frozen`，否则准备虚拟环境并安装锁定 requirements。子进程不经过 shell，Windows 使用 CREATE_NO_WINDOW 和独立进程组；stdout/stderr 持续排空写入时间戳日志，避免管道堵塞。失败保留窗口、日志和未完成进度。可见控制台入口为 `run_console.cmd`。启动窗需要标准 Python 的 Tcl/Tk；缺失时提示回退。

`desktop/win_native.py` 通过 Win32 提供项目级单实例互斥、图标托盘、任务栏重启后恢复和 Job Object。用户关闭进度窗后收起到托盘；无托盘则最小化保留控制窗口。菜单包括打开网页、查看状态、打开日志、停止并退出。只管理本次创建的进程，不根据端口任意结束别的服务。

状态探测禁用系统代理，直连 127.0.0.1。API 就绪要求目录哈希与实例 nonce 匹配。托盘退出先发受保护的 `/api/launcher/shutdown`，等待优雅停止，必要时才结束自己持有的子进程；Job 关闭补充清理子进程树。重复启动只打开本目录已有服务，不取得其停止权限。控制密钥只在子进程环境传递，不进入命令行、状态 API、会话文件或日志。常规 console 模式不开放该关闭功能。

运行文件位于 `data/launcher/`，已排除 Git 与发行包。原创 SVG 与多尺寸 ICO 放在 `static/`。Linux 可测启动逻辑、身份校验和隐藏进程参数，不能证明 Windows Tk、托盘、DPI 与实际进程退出体验。Windows 补验步骤见下文。

### 原站视窗

0.5 的“至少 1024 px 再缩小”不再作为默认。默认 responsive 使用实际容器宽度，scale 1；可选 scaled 以当前浏览器宽度取样作整体预览。`ResizeObserver`、窗口 resize 和展开／收回都会重算 iframe 尺寸。

`frameContainer` 是同一原生 dialog：内嵌时 non-modal，展开时提升到浏览器顶层，宽高为视口减两侧边距，iframe 填满工具栏之外的空间。展开和收回不替换、重挂 iframe 或重写 src，因此保留来源内的查询与滚动。关闭或切换条目／形态仍按正常流程清空旧来源。Esc 在展开状态收回正文。

跨域页面仍自行决定响应式布局和最小宽度。应用不能改写原站 CSS、读其私有内容或绕过 CSP / X-Frame-Options。来源可访问不代表允许嵌入；原站入口始终保留。视图状态允许 frameMode / frameExpanded，旧 frameFit 保持兼容。

### 导航与快捷命令

返回／前进从随内容滚动的控制移至正文左上角固定悬浮栏。位置根据页首和主栏实际矩形计算，resize 后更新；通知仍在右上角。窄屏目录尚占满页面时不覆盖目录。原有每标签页、每版本最多 60 个阅读快照和分支截断规则保留。

`static/interactions.js` 把翻页、随机、图片上／下张、日志／审核加载更多登记为安全命令。R 执行当前命令，页码、查询、范围在执行时取当前状态，不存旧 offset。忙时最多合并一次待执行重复，边界处停下。命令标注当前版本，关闭弹窗后不误用弹窗命令。N/P 是当前目录前／后页，Alt+方向键返回／前进，/ 搜索，? 查看说明，Esc 关闭当前浮层。

单键不抢输入、select、多选、contenteditable、IME 组合或 Ctrl/Meta/Alt 组合。iframe 内按键属于来源。Esc 和阅读返回不承担撤销数据库、设置或收藏的职责。滚动历史持久化去抖 220 ms，pagehide 最后落盘，避免每帧序列化整段历史。

### 动效先盘点后实施

完整方案与区域清单见 `docs/MOTION_DESIGN.zh-CN.md`。本次共享浮层进入／退出生命周期，含图片、设置、帮助、阅读抽屉和展开视窗。退出结束前维持 modal，结束后归还焦点；revision 防止旧动画回调关闭新打开的浮层。0 档和系统 reduced motion 结束效果并完成状态，不留下不可关闭窗口。

图片查看器提供上一张、下一张、计数和方向动画。设置固定外框，内容独立滚动；详情保持原生 summary 语义并保留原有输入节点。通知、收藏、选择确认、目录错峰、日志新增行、稳定 ID 列表 FLIP 和 3 档点击墨色反馈纳入同一体系。打印前结束过渡。没有固定 60 FPS JS 绘制循环；120 Hz 需要目标屏幕测量。

### 英文学名显示

审阅基线后发现三处中文注记：Thymus（属）、Cinnamomum（属）、Capsicum（原料属）。`scientific_en` 增加英文显示副本，规范括号和 genus 等注记。原始 scientific、条目 ID、检索身份及清洗证据不改写。英文目录、展签及身份卡使用显示副本，中文保留原始资料。

### README 与版本说明

`README.en.md`、`README.zh-CN.md` 为两份完整语言指南；`python scripts/build_readme.py` 生成默认 README，全文英文在前、中文在后。修改时编辑独立语言文件再生成首页。CHANGELOG 按新增、修改、修复维护，0.6 为 Unreleased；过去的本地包不追造 Git 标签或 Release。开发文档、历史及决策记录用中文维护。

作者身份与项目源码许可证仍由所有者决定，不自动指定 MIT 等授权。公开可见不等于开源授权。第三方文字、图像、音频及依赖来源声明单独维护。

## 数据与打包

基线仍有 18,379 条：92 个材料／混合物候选（含 13 个展签），18,287 个植物分类参考。审核档案 699 条：392 排除、101 待定、206 合并。0.6 没有将所有植物重新判定为香料，也没有声称完成成分、菜系、包装等全库事实审核。

源目录 cutoff 为 2026-10-27T04:34:04Z，实体证据与清洗为 2026-10-28。Git 使用可校验 gzip 种子；ZIP 使用一致性 SQLite backup，包含 desktop、图标、图形／控制台入口、双语文档及测试。排除虚拟环境、个人版本、配置密钥、运行日志、缓存、在线正文与照片。已有未知临时文件不删除、不打包。

## 可复现检查

```bash
uv sync --frozen
uv run python -m unittest discover -s tests -q
node --check static/app.js
node --check static/experience.js
node --check static/interactions.js
npm ci
npm run test:ui
python scripts/build_readme.py
python scripts/build_release.py
python scripts/verify_release.py ../Spice_Atlas_Local_v0.6.zip
```

Node 是可选开发工具；生产仍为 Python。无本地 Node 依赖时可设置 SPICE_LINKEDOM_PATH 指向已安装 LinkeDOM。三个 DOM 套件覆盖目录与版本、阅读体验、浮层与命令生命周期；它们是结构和行为检查，不是原生 Windows 或真实高刷新率测试。

浏览器使用 Sites managed preview，按 package.json 的 dev 指令运行明确标为 synthetic 的 QA 夹具。原站尺寸与输入保留测试使用合成本地页，不能当作真实 Bing 或 Google 的嵌入承诺。生产 Python API 和新解压目录 smoke 单独验证。最终数量、测量和限制见 `data/verification_v06.json`。

`verify_release.py` 检查 ZIP CRC、目录边界、Windows CRLF、启动文件、SQLite 完整性及中英首页顺序；在临时解压目录建立全新工作版本，进行 TestClient 首次启动与实际 uvicorn 本地 HTTP 就绪／受保护退出检查。该隔离检查禁用外站诊断，不使用个人密钥。QA 样本包含前五页植物参考及初始目录，未知样本明确报错，不再回退为欧芹；图库样本也不将欧芹照片用于其他条目。

## 本机验收顺序

1. 将新 ZIP 解压到新目录，保留旧目录备份。Windows 双击 run.cmd，确认依赖阶段有进度，CMD 不需常驻；初次下载时可打开详细日志。
2. 页面就绪后关闭启动窗，确认托盘仍可重新打开页面和日志；再次双击启动不产生同目录第二个服务。选择“停止服务并退出”，确认网页服务停止，托盘消失。
3. 分别试依赖安装失败、Tcl/Tk 缺失回退、8765 已占用，以及启动中点击停止；确认没有误杀其他进程或无提示地卡住。首次安装需联网。
4. 图片源切到允许嵌入的来源；默认实际宽度、缩放预览、展开／收回分别观察。先在原站输入，再展开／收回，检查查询不丢失。第三方拒绝嵌入时使用原站链接。
5. 正文滚动后仍能用左上角返回／前进。目录点击下一页，再用 R、N/P；输入搜索时这些字母应正常输入，IME 期间不跳页。
6. 3 档下检查图片打开／退出、左右翻图、设置标签、帮助、详情、通知和列表排序；切 0 档或系统减少动态效果，功能即时可用。
7. 英文目录检查 Thyme / Cinnamon / Paprika 的学名备注；对比完整中英 README、来源和许可链接。

## 保留边界与发布门槛

用户 LM Studio、个人 Google/Azure 凭据、Windows 原生桌面、语音包可听输出和 120 Hz 屏幕没有由 Linux 环境替代验证。全文翻译、全库人工烹饪知识审核、视频生成、完整作者／许可页和 GitHub 自动更新仍未实施。

先完成检查并交付候选包。**用户明确验收并允许前，不 commit、不 push、不部署、不创建 GitHub Release。** 获准提交后应核对文件范围与验证记录，不将个人运行数据或密钥加入仓库。

界面测试夹具在 Git 中采用 `tests/ui_fixtures.json.gz` 无损压缩保存，`fixture_service.cjs` 用 Node 标准库解压，仍兼容旧包中的 JSON。`tests/export_ui_fixture.py` 默认生成压缩夹具，也可显式传入 JSON 输出路径。此调整用于减小源码同步请求，不改变测试资料或应用行为。
