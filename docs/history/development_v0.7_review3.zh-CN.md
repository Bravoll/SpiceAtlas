# v0.7 开发与验收说明

日期：2026-10-29，第三次审查修订。保留版本 0.7.0；本轮不 commit、不 push、不部署。基于已同步 v0.6 源码 `9e02c9fdaaf6a106e05ed37acfa5928b8640f4d8`。前一次候选说明保存在 `docs/history/development_v0.7_review1.zh-CN.md`，v0.6 记录也保留。

## 本轮变更

新增 `atlas/wiki_languages.py` 英文锚点、语言映射及独立搜索校验，`atlas/web_sources.py` 专业正文／公开检索／实际 frame 检查，`static/wiki_reader.js` 独立 Wiki 选项及详情导航，`desktop/browser.py` 可靠打开回环网页。`static/text_motion.js` 改用有界真实文本单元，主题即时应用；启动日志增加竖向滚动条。

详见 [第三次修订](../V07_REVIEW3.zh-CN.md) 和 [动效调查](../MOTION_RESEARCH_v0.7_review3.zh-CN.md)。默认其他来源预算调整为单源 25 秒、整轮 35 秒，保留已有配置。注册表现为 21 组；原 184 条研究的 19 组统计保留为历史。Google SAMEORIGIN、百度验证与实际 API 资格不能由本机强制消除。

## 既有实现与本轮保留


- `desktop/gui.py` 采用实际控件测量和自适应换行，控制区两列；详情显隐记住分别大小，终端继续显示运行请求。托盘单击显隐、双击打开及 tooltip 保持前一候选语义。
- `atlas/runtime.py`、`main.py` 提供 SSE 事件；先通知即将暂停，450 ms 后执行内容门禁，随后更新同卡。继续时同实例恢复并要求手动重测，暂停期间允许状态、通知与管理控制。已有外部请求按边界或有界超时结束。
- `atlas/health.py` 固定 2000 ms 一次发布、600 秒后重测；超时标记未确认，保留旧可用性，首次乐观开启；明确失败才禁用。浏览器结果逐项上报，不扣留快请求，迟到轮次仍拒收。与 v0.6 的阅读流程比较后，自动正文恢复实际 Wiki 映射／请求回退，不拿搜索页替代。
- `atlas/providers.py` 精选文件先查实时 Commons imageinfo 元数据，关键词为备选，首个有效候选即可呈现；包装筛选独立。正文解析在工作线程，避免闲置预取解析阻塞事件循环。
- `static/notifications.js` 通用通知队列、1.5 倍感应圈、面板四边外扩、快速点击保护及可中断反向收起；状态轮询补充 SSE。
- `static/catalogue_navigation.js/css` 四个有界区域、按高度定容量、子集／条目独立分页、区域 sticky 和鼠标驻留控件。低频管理只在设置。[ / ] 和 , / . 分别翻页，可改键。翻页、分类、区域滚动进入阅读操作历史。
- `atlas/anticipation.py`、`atlas/cache_memory.py`、`static/remote_cache.js` 实现在线操作三列统计、加权深度一预测、资源包字典及访问次数、六次长期留存、第一页／收藏闲置预热。预测载荷只进有界 RAM，用户操作取消旧代次。
- 保留前候选的终端脱敏、语言／知识源文字动效和“其他来源”流式完整卡片。原 19 组提供方、184 条分层样本、257 个候选链接及指定引擎失败记录未被新修订改写。

详细设计见 [本轮回归修复](../V07_REVIEW_FIXES.zh-CN.md)、[缓存规则](../CACHE_DESIGN.zh-CN.md)、[交互盘点](../MOTION_DESIGN.zh-CN.md)和[来源调查](../SOURCE_RESEARCH_v0.7.zh-CN.md)。目录基线仍为 18,379 条、699 条清洗决定，植物参考不代表食用确认。

## 检查与打包

```bash
uv sync --frozen
uv run python -m unittest discover -s tests -q
npm run test:ui
uv run python scripts/build_readme.py
uv run python scripts/build_release.py
uv run python scripts/verify_release.py ../Spice_Atlas_Local_v0.7.zip
```

Node 仅供可选检查；未在项目安装 node_modules 时可用 SPICE_LINKEDOM_PATH 指向 LinkeDOM。当前测试数量、真实浏览器尺寸及实际包验收以 `data/verification_v07.json` 和包外验收报告为准，不能将计划检查当成已通过。

浏览器使用明确标记的合成百科预览，独立测量 1100×820、1000×620、1000×500 与窄屏 680×820 容器；检查完整条目、常驻范围、翻页按钮和通知。真实 Wiki 正文／Commons 图片读取另存 `data/source_research/live_reading_revision_v07.json`，仅摘要、不随包分发正文或图片。

发行验收在隔离新目录检查 CRC、安全路径、无个人版本／密钥、SQLite 完整性与条数、README 组成和全部新增资产；实际启动受控本地 HTTP 进程，验证暂停前 SSE 到达而门禁未关、暂停后 503 和通知可关闭、继续同实例并等待手动诊断、受保护停止及正常进程退出。

## 本轮检查补充

`tests/test_v07_review3.py` 覆盖语言关联、无关联搜索校验、GBIF v2/v1、代理 DNS／私网防护、PlantNET 目标识别、真实 framing 检测及 Windows Shell／就绪后打开。`tests/reading_review3_acceptance.cjs` 覆盖文字和表格语义、主题同步生效、语言竞态、加载后滚动、首页重置及检索详情返回／前进。

真实浏览器受控延迟时，正文提交前后都停留在 1229 px；实际联网读取摘要在 `live_readers_v07_review3.json`，不将合成 API 当作真实来源。

## Windows 本机重点验收

1. 完整解压新目录，双击启动，检查自动打开默认浏览器、两排控制均完整、换行及 DPI 缩放不裁切；同一按钮展开／隐藏日志，右侧滚动条和“跳到最新”可用，后续请求继续输出。保持日志不含凭据。
2. 托盘悬停名称、单击显隐、双击开网页及右键暂停／继续／退出。关闭窗口保留服务，停止只终止自己创建的实例。
3. 暂停前先收到通知，暂停后同卡更新；继续另发通知，点击重测才恢复诊断轮次。进程和端口不变。
4. 铃铛扩大感应圈，面板四边缓冲，移开反向收起；迅速靠近点击不误删。连续关闭保持按钮原位。
5. 改变浏览器高度，左栏条目不出界；悬停连续翻页和两组自定义按键正确。查看缓存三列表、六次留存、收藏预热与版本复制。
6. 3 档词／单字过渡、局部主题光晕、下拉及弹窗进出和反复中断；0 档及系统减少动态效果无残留。其他来源卡片逐张完成、独立阅读、停止和换条目不串页。

Linux 检查不能代替 Windows 原生视觉、设备音频或 120 Hz 实测。个人 LM Studio／Google／Azure 凭据未连接；第三方嵌入权限、站点可达性仍按实际网络显示。多风格预设及其调查继续暂缓；源码许可证、完整作者 About 和 GitHub 更新器仍待后续决定。

本版先打包供审查；此次没有提交／推送授权。
