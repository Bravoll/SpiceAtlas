"""Compile fixed UI labels for Simplified, Traditional and English."""
import json,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bs4 import BeautifulSoup
from atlas.localization import to_hant
root=Path(__file__).resolve().parents[1]
text='''sourceCutoff	源目录截止	Source catalogue cutoff
cleanedAt	清洗时间	Cleaned at
lastSync	最近同步	Last synchronized
imageProfile	图片形态筛选	Image form filter
followForm	跟随原料形态	Follow material form
imagesOnly	仅影响图片检索	Image search only
versions	版本	Versions
favorites	收藏	Favorites
history	浏览历史	History
collections	收藏与历史	Saved lists
logs	操作日志	Activity log
about	关于与说明	About & help
collectionMode	查看列表	View list
favoriteAdd	☆ 收藏	☆ Save
favoriteRemove	★ 已收藏	★ Saved
translationService	翻译服务	Translation service
localModel	本地模型	Local model
disabled	关闭	Off
excludeLanguages	不自动翻译的来源语言（可多选）	Source languages to exclude (multiple)
enableLocal	启用本地模型连接与启动检测	Enable local model & startup check
cloudTranslation	云端翻译密钥	Cloud translation credentials
clearGoogleTranslation	删除 Google 翻译密钥	Clear Google translation key
clearAzureTranslation	删除 Azure 翻译密钥	Clear Azure translation key
cloudHelp	使用官方 Google Cloud / Azure API，需要自己的密钥和配额；与图片搜索 API 分开。启动检测会发送一小段欧芹测试文字，可能计入用量。	Official Google Cloud / Azure APIs require your own credentials and quota, separate from image search. Startup checks send a tiny Parsley translation and may count toward usage.
auditArchive	清洗审核档案	Data cleaning archive
viewAudit	查看排除与待审核记录	View excluded & pending records
versionHelp	每个版本独立保存目录、设置、缓存、图片词库、收藏、历史和日志。版本管理与列表排序保存在版本外。删除的版本可以恢复。	Each version contains its own catalogue, settings, cache, image vocabulary, favorites, history and logs. The manager and version ordering are stored separately. Deleted versions can be restored.
versionName	新版本名称	New version name
createFrom	创建方式	Create from
copyVersion	复制所选版本	Copy selected version
defaultVersion	内置目录与默认设置	Built-in catalogue & defaults
sourceVersion	复制来源	Source version
sortBy	排序	Sort by
customOrder	自定义	Custom order
sortName	名称	Name
sortCreated	创建时间	Created
sortModified	修改时间	Modified
sortDirection	方向	Direction
ascending	升序	Ascending
descending	降序	Descending
createVersion	新建版本	Create version
dragHint	拖动把手调整顺序，也可以使用上下箭头。修改名称后点击重命名。	Drag handles or use arrow buttons to reorder. After editing a name, click Rename.
deletedVersions	已删除的版本	Deleted versions
savedList	长期列表	Saved list
historyOrder	历史排序	History order
recentFirst	最近浏览优先	Recently visited first
logScope	日志范围	Log scope
currentVersion	当前版本	Current version
versionManager	版本管理	Version manager
refresh	刷新	Refresh
more	加载更多	Load more
aboutIntro	用于逐步探索植物、调味原料、文化与来源的本地资料阅读器。	A local reader for exploring plants, culinary materials, cultures and their sources.
sourcePolicy	语言与来源排序	Language & source order
serviceHelp	连接检测与临时禁用	Connection checks & temporary filtering
imageVocabulary	图片关键词库	Image search vocabulary
licenseHelp	百科正文与图片保留各自来源、作者与许可。API 引用不会免除许可要求。植物参考记录不代表可食用。作者署名、项目开源许可与 GitHub 更新功能后续再加入。	Article text and images retain their source attribution and licenses. API access does not remove license requirements. Botanical references do not confirm edibility. Project authorship, open-source licensing and GitHub updates are deferred.
rename	重命名	Rename
switchVersion	切换	Switch
remove	删除	Delete
restore	恢复	Restore
active	当前	Active
createdAt	创建	Created
modifiedAt	修改	Modified
moveUp	上移	Move up
moveDown	下移	Move down
notificationSummary	{count} 条来源通知 · 点击查看	{count} source notice(s) · View details
dismiss	关闭通知	Dismiss
healthChanged	来源连接状态发生变化	Source availability changed
serviceRecovered	已恢复	Recovered
serviceDisabled	临时禁用	Temporarily disabled
refreshPending	下次内容操作将保留当前状态并刷新页面。	Your next content action will preserve the current view and refresh the page.
healthChecking	正在后台检测（欧芹 / Parsley）	Checking in background (Parsley)
backendRoute	后台连接	Backend route
browserRoute	浏览器直连	Browser route
frameRestricted	网页可访问，但禁止嵌入	Page reachable; framing restricted
apiUnavailable	API 暂不可用	API temporarily unavailable
primaryLanguage	优先语言	Preferred language
secondaryLanguage	另一语言	Other language
sourceKindExternal	来源网页／搜索	Source website / search
sourceKindReference	资料来源	Reference source
translated	机器译文	Translation
translationReady	机器译文 · 尚未人工核实	Machine translation · not human reviewed
translationLoading	正在通过所选服务翻译；原文仍可阅读…	Translating with the selected service; the original remains available…
modelNotReady	请在设置中启用并配置翻译服务。	Enable and configure a translation service in Settings.
autoTranslate	使用所选服务自动翻译不同语言的重点段落	Automatically translate focus paragraphs with the selected service
modelSettings	翻译服务	Translation services
allSourcesFailed	维基来源暂时无法连接，仍可查看可用的其他来源。	Wikipedia sources could not be reached. Other available sources remain accessible.
cutoff	数据截止／同步信息	Catalogue cutoff / sync metadata
vocabStats	{materials} 个原料 · {queries} 次真实检索 · {profiles} 类形态	{materials} materials · {queries} recorded searches · {profiles} image profiles
notSpecified	未记录	Not recorded
cleaningCounts	排除 {excluded} · 待审核 {pending} · 合并 {merged}	Excluded {excluded} · Pending {pending} · Merged {merged}
noServices	当前没有可用来源；连接会在后台重试。	No sources are currently available; checks will retry in the background.
loadingLocal	正在查询本地目录…	Searching the local catalogue…
cloudNoKey	未配置的服务不参与启动检测。	Unconfigured services are omitted from startup checks.
help_depth	起始分类是第 0 层。设为 2，会读取起始分类、子分类和子分类的子分类。这是维基目录的链接深度，不是植物学上的科、属、种等级。	The starting category is level 0. Depth 2 reads that category, its subcategories, and their subcategories. This is Wikipedia category-link depth, not botanical family, genus or species rank.
help_budget	200 指本次任务最多处理 200 个分类目录，不是 200 个香料条目。达到上限会保存队列和分页游标并暂停；提高上限后点击继续，不必重新导入。	200 limits the number of category directories processed by this job, not the number of material records. The queue and pagination cursor are saved at the limit. Increase the budget and Resume to continue.
help_policy	仅“自动＋系统简体中文”优先百度百科、国内 Bing、其他资源。其他模式（包含手动简体、手动繁体、自动繁体及英文）优先对应语言维基、国际 Bing、Google、其他资源，再列另一语言。设置中的正文语言独立于界面；没有中文维基时可显示英文并自动翻译。	Only Auto with a Simplified Chinese browser prioritizes Baidu Baike, Bing China and other resources. All other modes, including manual Simplified or Traditional Chinese, prioritize matching-language Wikipedia, Bing International, Google and other resources, followed by the other language. Article language is independent of the interface. English Wikipedia can be translated when Chinese is missing.
help_health	启动时以欧芹 / Parsley 检查网页、API 及已配置的功能服务，并每 10 分钟重试全部服务。网络失败与禁止嵌入分开记录。全部正常时不通知；状态变化通知需手动关闭。布局变更延迟到下一次内容操作，并保留条目、形态、列表和阅读位置后刷新。浏览器直连可与后台网络结果不同。	Startup checks use Parsley for webpages, APIs and configured functional services, then recheck all services every 10 minutes. Connection failure and framing restrictions are distinct. Healthy checks are silent. Change notices persist until dismissed. Layout changes wait for the next content action, then reload while preserving the entry, form, list and reading position. Browser and backend connectivity can differ.
help_images	图片形态词库来自多种代表性原料的 Commons 文件名实测，查询和时间保存在研究记录中。鲜叶、干叶碎、粉末、整粒、树皮、花蕾、根、切片、罐装和袋装分别组合检索。仅影响图片排序；候选图仍应核对对象和文件说明，包装不等于植物身份。	Image-form vocabulary uses recorded Commons filename searches across representative materials. Fresh leaves, flakes, powder, whole seeds, bark, buds, roots, slices, jars and bags use distinct queries. This affects image retrieval only. Verify candidate subjects and file descriptions; packaging is not botanical identity.
help_versions	复制会暂停来源版本的导入任务并保存可续传状态；内置默认版本不含你的密钥、收藏或历史。切换后异步请求继续归属于发起版本，旧标签页写入会被拒绝。版本删除进入可恢复区；版本管理日志单独保存。	Copying pauses imports and preserves resumable progress. A default version includes no personal keys, favorites or history. Async requests stay with their originating version, and stale tabs cannot write into the new active version. Deleted versions are recoverable. Manager logs are stored separately.'''
text+='''
photosDirect	浏览器实时加载远程图片	Remote images loaded by your browser
sourceWindowShown	原站搜索视窗已开启，随容器适应；也可打开上方原站链接。	Source window open and fitted to this container; original-site links remain above.
goBack	返回	Back
goForward	前进	Forward
randomExplore	随机探索	Surprise me
openElsewhere	新窗口	Open elsewhere
fitWindow	适应视窗	Fit window
nativeWindow	原始尺寸	Native size
adaptiveFrameNote	适应模式随视窗缩放原站页面。原站排版与嵌入权限由来源控制；若空白，可打开原站。	Fit mode scales the source page as this viewport changes. Layout and embedding permissions remain controlled by the source; open the original if the frame is blank.
readingComfort	阅读排版与动态效果	Reading comfort & motion
readingComfortNote	正文文字可独立调整，右侧 Aa 标签可随时打开快捷栏。	Resize article text independently. The Aa tab at the right opens reading shortcuts at any time.
openReadingTools	打开阅读快捷栏	Open reading shortcuts
readingTools	阅读	Reading
done	完成	Done
drawerIntro	调整仅作用于文章文字。点击外侧即可保存并继续阅读。	Adjust article typography without scaling the interface. Click outside to save and continue reading.
fontSize	正文字号	Article text size
fontSmall	小	Small
fontStandard	标准	Regular
fontLarge	大	Large
fontExtra	特大	Extra
lineHeight	行间距	Line spacing
readingFont	正文字体	Article typeface
fontSerif	书页 · 衬线	Book · Serif
fontSans	清晰 · 无衬线	Clear · Sans
fontKai	手稿 · 楷体	Script · Kai
animationLevel	动画层级	Motion level
motion0	0 · 无动画	0 · Still
motion1	1 · 轻量	1 · Minimal
motion2	2 · 舒适	2 · Refined
motion3	3 · 艺术	3 · Botanical
motionNote	动画遵循系统“减少动态效果”。最高档使用浏览器原生合成动画，实际帧率由屏幕与设备决定。	Respects your system’s reduced-motion preference. The highest level uses native browser animation; the display and device determine the actual frame rate.
readingSample	一片叶，一段风味的旅程。Every leaf holds a story.	Every leaf holds a story. Follow the quiet journey from plant to spice.
resetReading	恢复阅读默认	Reset reading defaults
startupMode	启动时展示	On startup
startupResume	继续上次阅读	Continue last reading
startupBasil	固定罗勒	Always open Basil
startupRandom	随机一个条目	Open a random record
randomScope	随机探索范围	Random exploration scope
listenEnglish	英语发音	Hear English
ipaUnavailable	英式语音优先；音标缺失或暂不可用时不生成。	British voice preferred; IPA is shown only when sourced.
pinyinNote	自动生成的普通话拼音，多音字及专名应以可靠词典为准。	Automatically generated Mandarin pinyin. Check a reliable dictionary for polyphonic characters and proper names.
pinyinAuto	自动拼音	Auto pinyin
pronunciationSource	词典来源 ↗	Dictionary source ↗
speechUnavailable	本机暂未提供可播放的英语语音。请安装系统英语语音包，或稍后重试词典音频。	No usable English voice is available. Install an English system voice, or retry dictionary audio later.
speechBritish	浏览器合成语音 · en-GB	Browser speech · en-GB
speechSystem	已请求 en-GB；本机可用口音由语音包决定。	Requested en-GB; the available accent depends on installed voices.
speechRecording	词典英式录音	British dictionary recording
help_pronunciation	进入条目时读取公开词典 API 的英语音标，并保留词典链接。播放优先使用标为 UK / GB 的词典音频，否则调用浏览器 Web Speech API，优先选择 en-GB 语音；本机没有英式语音包时会明确提示。中文拼音由本地 pypinyin 自动生成，多音字应核实；拉丁学名不合成朗读。词典或音频临时不可用时不会编造音标。	English IPA is retrieved from a public dictionary API with a source link. Playback prefers a UK / GB recording, then browser Web Speech with an en-GB voice. If a British voice is unavailable, the interface says so. Mandarin pinyin is generated locally by pypinyin and should be checked for polyphonic characters. Latin taxonomic names are not synthesized. Unavailable IPA is never invented.
help_reading	右侧 Aa 快捷栏可调整正文字号、行距、衬线／无衬线／楷体字体与四档动画。点击外侧或完成会保存到当前版本，保存失败时保留面板。0 关闭动画，1 轻量，2 常规细节，3 植物晕染与更丰富的过渡；系统减少动态效果优先。返回／前进记录最近 60 个阅读操作，包含条目、形态、来源、图片筛选、目录、阅读模式与位置；回退后新操作清除前进分支。设置或收藏修改不会被撤销。	The Aa drawer adjusts article size, spacing, typeface and four motion levels. Clicking outside or Done saves to the current version; failed saves keep the drawer open. Motion levels are 0 Still, 1 Minimal, 2 Refined and 3 Botanical, with system reduced motion taking priority. Back / Forward remembers up to 60 reading states including entry, form, source, image filter, catalogue, reading mode and position. A new action after going back discards forward states. Settings and saved-list changes are not undone.
pronunciationHelp	音标、拼音与发音	IPA, pinyin & pronunciation
navigationHelp	阅读快捷栏与导航	Reading shortcuts & navigation'''
text+='''\nresponsiveWindow	自适应宽度	Responsive width
scaledWindow	缩放预览	Scaled preview
expandWindow	放大视窗	Expand window
collapseWindow	收回视窗	Return inline
adaptiveFrameNote	按当前视窗宽度加载原站，完整查看可放大视窗。原站内部排版与嵌入权限仍由来源控制。	The source uses the current viewport width. Expand the window for a full browser-width view. The source controls its own layout and embedding permissions.
sourceWindowShown	原站搜索视窗已开启；可自适应宽度、切换缩放预览或放大查看。	Source window open. Use responsive width, scaled preview or expand it for more space.
repeatAction	重复上次操作	Repeat last action
catalogNextLabel	目录下一页	Next catalogue page
catalogPreviousLabel	目录上一页	Previous catalogue page
imageNextLabel	下一张图片	Next image
imagePreviousLabel	上一张图片	Previous image
auditNextLabel	加载更多审核记录	More audit records
logsNextLabel	加载更多日志	More log entries
keyboardShortcuts	键盘快捷键	Keyboard shortcuts
shortcutHint	? 查看快捷键	? Keyboard shortcuts
repeatHelp	Repeat：在当前状态重复最近一次可重复操作，如目录翻页、随机探索、图片切换或加载更多。	Repeat the last repeatable command against the current state: paging, random exploration, image stepping or loading more records.
pageShortcutHelp	Next / Previous：当前本地目录的下一页／上一页。	Next / Previous page in the current local catalogue.
navigationShortcutHelp	返回／前进至之前的阅读状态。	Back / Forward through reading states.
escapeShortcutHelp	关闭当前浮层；阅读侧栏先保存。原站放大视窗收回到页面内。	Close the current popup, saving reading-drawer changes first. An expanded source window returns inline.
searchShortcutHelp	聚焦左侧的本地搜索。	Focus the local catalogue search.
imageShortcutHelp	图片查看器中切换上一张／下一张。	Previous / next image while the image viewer is open.
shortcutsShortcutHelp	打开此快捷键说明。	Open this shortcut reference.
shortcutSafety	输入框、下拉选择、可编辑区域及输入法组合输入时，不抢占单键。原站内嵌网页中的输入由原站处理。Esc 不撤销数据库、设置或收藏。	Single-letter shortcuts do not capture input fields, selects, editable text or IME composition. Embedded websites handle their own input. Escape does not undo database, settings or saved-list changes.
help_reading	右侧 Aa 快捷栏独立调整正文。返回／前进悬浮于正文左上角，最多记录 60 个阅读状态。R 在当前状态重复上次可重复操作，N/P 目录翻页；Alt+方向键浏览历史，? 查看快捷键。0–3 动画覆盖弹窗进入与退出、列表与状态，系统减少动态效果优先。	The Aa drawer adjusts article typography independently. Back / Forward floats at the top left of the reading pane and retains up to 60 reading states. R repeats a command against the current state, N/P page the catalogue, Alt+arrows navigate history and ? opens help. Four motion levels cover popup entry/exit, lists and status; system reduced motion takes priority.'''
zh={};en={}
for line in text.splitlines():
 key,a,b=line.split('\t');zh[key]=a;en[key]=b
for el in BeautifulSoup((root/'static/index.html').read_text(),'html.parser').select('[data-i18n]'):zh.setdefault(el['data-i18n'],el.get_text())
# Static labels supplement the original dynamic dictionary, which remains authoritative for existing values.
script='"use strict";\nObject.assign(window.ATLAS_I18N.zh,'+json.dumps(zh,ensure_ascii=False)+');\nObject.assign(window.ATLAS_I18N.en,'+json.dumps(en,ensure_ascii=False)+');\nwindow.ATLAS_I18N["zh-Hans"]=window.ATLAS_I18N.zh;\nwindow.ATLAS_I18N["zh-Hant"]='+json.dumps({k:to_hant(v) for k,v in zh.items()},ensure_ascii=False)+';\n'
# Fill traditional dynamic labels too, by parsing the original JSON-like JS object through Node.
import subprocess
out=subprocess.check_output(['node','-e','global.window={};require("./static/i18n.js");process.stdout.write(JSON.stringify(window.ATLAS_I18N.zh))'],cwd=root,text=True)
allzh={**json.loads(out),**zh};script=script[:script.index('window.ATLAS_I18N["zh-Hant"]=')]+ 'window.ATLAS_I18N["zh-Hant"]='+json.dumps({k:to_hant(v) for k,v in allzh.items()},ensure_ascii=False)+';\n'
(root/'static/ui_strings.js').write_text(script)
