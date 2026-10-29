# v0.5 开发与验收说明

日期：2026-10-29（澳大利亚东部夏令时间）。状态：本地待验收，未 commit、未 push。

本次在私有仓库的 v0.4 工作树上制作 0.5。用户要求先交付可运行压缩包，验收通过并明确允许后再提交和推送。旧版开发说明保存在 `docs/history/`；不改写历史验证结果。

## 本次最终行为

### 阅读布局与图片视窗

图片标题和形态筛选归入左组，来源按钮、刷新和新窗口入口归入右组。使用两端对齐和中间留白，窄容器再分行，避免把所有对象挤在同一排或垂直叠成长列表。

文章区域采用更宽的主列；容器不够宽时章节侧栏移到下面，正文不被固定窄栏压缩。桌面外层固定在视口，目录和主内容各自滚动；窄屏规则保留页面滚动。

原站 iframe 外包独立 viewport。`ResizeObserver` 观察容器，窗口变化时也重算。适应模式以至少 1024 CSS px 的源站排版宽度取样，按容器宽度计算缩放，反向扩展 iframe 高度，保持可用显示高度；原始模式使用容器宽度、scale 1。不能跨域修改 Bing 等原站自己的样式，也没有移除嵌入限制。

### 独立阅读排版

新增 `static/experience.js`、`static/experience.css`。右侧 Aa 标签打开原生 modal dialog 侧栏，提供 14–28 px、行距 1.5–2.3、衬线／无衬线／楷体及常用字号预设。只改变正文和排版试样，界面尺寸不随之变化。

输入时预览草稿，完成、点击外侧或 Escape 发送只含阅读字段的补丁。失败保留面板和错误；成功保存所属工作版本后关闭。不会把空的模型密钥等其他设置一并提交。

### 动态效果

`animation_level` 为 0–3，默认 2。0 停止应用动画和顺滑滚动；1 轻量反馈；2 增加内容、抽屉和主题揭示；3 增加多层植物色彩晕染和更丰富的细节。

主题切换优先使用 View Transitions，其他动效使用 CSS / Web Animations API 的 transform、opacity 等原生动画；无固定帧率循环和持续空转绘制。缺少 API 时保留功能。`prefers-reduced-motion` 优先，将有效档位归零。不能以这种实现方式推断已达到 120 Hz；本次预览环境未提供高刷新率屏幕测量。

### 英语发音和中文拼音

`atlas/pronunciation.py` 通过公开 Free Dictionary API 只提取匹配单词的音标和音频。音频域名、协议及路径经过允许列表校验，前端仍转义文本；来源与服务提供的许可保留。UK / GB 记录优先，US 不冒充英国音频。浏览器不能播放词典英式音频时，调用 Web Speech，优先选 en-GB；本机缺少英式语音时明确说明。朗读只能由用户点击触发。

没有音标不生成，连接失败不作为“词条无音标”的证据。正结果缓存 30 天，空结果 6 小时，暂时失败 10 分钟；切换条目停止旧朗读、丢弃迟到响应。同版本同单词请求合并。词典 API 纳入后台诊断，暂不可用时仍保留浏览器语音路径。

中文通过本地 pypinyin 产生有声调拼音，保留自动标记。与学名相同的英文栏不调用合成朗读；不为拉丁学名提供专门音标或 TTS。声卡可听输出、用户机器的语音包和具体口音须本地验收。

### 操作导航、随机与启动

随机接口 `/api/catalog/random` 只从当前工作版本的已准入本地 entries 均匀抽取，排除当前项，默认限 culinary，不查远程源、不抽 quarantine。可设置包含植物参考，但不能将随机结果解释为可食用性。

`startup_mode`：resume / basil / random。明确的外部条目 URL、服务布局变更后的操作恢复优先；新工作版本默认罗勒。自动生成的浏览器 URL 会用 history state 区分，避免刷新时错误覆盖启动策略。

操作导航保存每标签页、每工作版本最多 60 个安全阅读快照，覆盖条目、形态、来源、图片筛选、目录查询和层级、阅读模式、窗口模式、内部章节与滚动位置。不保存模型配置和密钥，不撤销设置或数据库变化。

原生 pushState / popstate 配合页面返回前进；新操作截断 forward 分支。内部锚点点击走同一导航流程，避免额外 hash 记录干扰栈。切换工作版本或恢复较早会话时，只有已知连续的原生历史区间才调用 history.go，其余由本地快照恢复。达到上限会淘汰最早记录。

服务状态变更仍延迟至下一次内容操作全局刷新；刷新前保存安全视图和待执行操作，刷新后恢复并续行。导航日志在该流程中保留，版本切换仍受 X-Atlas-Version 边界约束。

### 首次诊断

`resources.available` 对 phase=checking 统一保持可用，不依据初始的局部失败先隐藏来源。`Health.check` 收集完整一轮结果再 publish；浏览器探测先返回也不会单独生成初始失败通知。完成之后才临时禁用和通知。后续仍每 600 秒重测全部服务。

## 设置与接口

新增版本内设置：

| 字段 | 默认值 | 范围 |
| --- | --- | --- |
| reader_font_size | 17 | 整数 14–28 |
| reader_line_height | 1.85 | 1.5–2.3 |
| reader_font | serif | serif / sans / kai |
| animation_level | 2 | 整数 0–3 |
| startup_mode | resume | resume / basil / random |
| random_scope | culinary | culinary / botanical / all |

`/api/entry/{id}` 新增 pinyin、pinyin_automatic、spoken_english；`/api/pronunciation/{id}` 返回带来源的字典元数据。View-state 允许字段补上 imageProfile、frameOpen、frameFit、windowScroll 和 anchor。其他未知字段仍不会写入。

Python 依赖新增 pypinyin，uv.lock 和 requirements.txt 同步更新。Node package 仅供可复现的可选界面测试和合成预览，生产运行仍使用 Python。

## 数据与打包

基线继续为 18,379 条：92 个材料／混合物候选，18,287 个植物分类参考；699 条审核档案为 392 排除、101 待定、206 合并。0.5 没有声称完成新一轮全库烹饪知识审核。

源目录 cutoff 为 2026-10-27T04:34:04Z，实体证据和清洗为 2026-10-28。实体原始资料、清洗理由和图片关键词样本保留。正文、图片和录音按需获取；不随新包分发在线正文或照片。

`build_release.py` 从 pyproject 读取版本，统一包名和顶层目录。包内有纯净基线、双语 README／CHANGELOG／来源声明、中文开发与决策文档、历史记录、测试和启动脚本。没有 Git 凭据、版本私有配置、个人收藏／历史、虚拟环境或运行缓存。

Git 源码继续使用可校验的 gzip 种子。ZIP 则放一致的 SQLite backup；不复制活动工作空间。不要将旧 baseline 或 data/versions 直接覆盖新发行包进行验收。

## 运行检查

```bash
uv sync --frozen
uv run python -m unittest discover -s tests -q
node --check static/app.js
node --check static/experience.js
npm ci
npm run test:ui
```

不安装 Node 依赖时，也可以令 SPICE_LINKEDOM_PATH 指向外部 LinkeDOM，再分别运行 `node tests/ui_acceptance.cjs`、`node tests/experience_acceptance.cjs`。

本环境真实浏览器预览沿用 Sites 的 managed preview，通过 `package.json` 的 dev 指令运行 `tests/preview_fixture.mjs`；它明确标为合成正文，不冒充生产 API。原站视窗测试也使用明确标为 synthetic 的本地页面，生产连接和第三方 framing 能力仍由真实接口判断。

最终自动化、浏览器测量、交付包 smoke 和限制记录在 `data/verification_v05.json`。三个单词的实际字典请求记录在 `data/verification_v05_live.json`，含失败，不把模拟 UK 数据算作真实音频验证。

## 发布与文档约定

- README.md 为完整英文默认首页，README.zh-CN.md 为中文说明。
- CHANGELOG 两种语言分别按新增、修改、修复维护；早期追补标明证据边界。
- v0.1 保留的是设计说明，不伪造已运行的接口、测试、Git 标签或提交。
- development.md 和 docs/CONVERSATIONS.zh-CN.md 使用中文维护。决策文档不包含私人登录过程和密钥。
- 未决定完整作者与源码许可证，不擅自添加 MIT 等项目授权；第三方许可单独列明。
- 0.5 待用户验收，当前不 commit、不 push、不部署、不创建 GitHub Release。

## 当前验证限制

未连接用户 LM Studio，未用个人云翻译凭据。浏览器检查为桌面环境；图片候选未逐张人工鉴定，音标和拼音不是植物身份或食用证据。没有测量用户电脑语音包的可听输出、移动设备或 120 Hz 屏幕。外站可能限速、超时或禁止嵌入，保留来源链接和浏览器语音等正常回退路径。

全文翻译、全库成分／菜系／包装事实核实、视频生成、完整作者与项目许可页和 GitHub 自动更新仍在后续范围。
