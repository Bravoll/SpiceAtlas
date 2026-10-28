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
