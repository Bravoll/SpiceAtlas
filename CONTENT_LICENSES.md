# 内容、图片与署名

本版随包保存目录元数据、清洗决策和 Wikidata 结构化证据，不分发百科正文快照或下载图片。研究抽查用过的维基简介全文不随发行包提供，保留原页、获取时间和历史入口索引。使用过程中获取的文本、图像和译文仍遵循各来源许可，缓存与直链不会改变许可。

## 维基百科文本与分类

正文经 MediaWiki Action API 获取，记录原文地址、固定版本、作者历史、获取时间与许可入口。显示时清理脚本、统一排版、去除正文图片、改写相对链接和引用锚点；重点模式按原章节筛选。启用本地或云端翻译时另标为机器译文。

维基百科文本通常采用 CC BY-SA，具体以原页和适用条款为准。分类标题、页面名称等来源数据保留站点和原始标识；本项目不把第三方文本重新授予其他许可。

- [Wikimedia 使用条款](https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use)
- [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
- [MediaWiki 分类成员 API](https://www.mediawiki.org/wiki/API:Categorymembers)

## Wikidata

名称、别名、站点对应关系、学名及主图文件名来自 Wikidata 结构化数据，按 CC0 提供。对应图片文件本身的许可并不因此变成 CC0。

- [Wikidata 许可](https://www.wikidata.org/wiki/Wikidata:Licensing)

## GBIF 植物分类元数据

本版使用 GBIF Secretariat 发布的 GBIF Backbone Taxonomy 数据集，键为 d7dddbf4-2cf0-4f39-9b2a-bb099caae36c，数据集页面列明 CC BY 4.0。发布日为 2023-08-28；本包同步日为 2026-10-27。

范围为唇形科、伞形科、胡椒科中该数据集的 accepted species 记录；保留来源记录键、学名、科／属和来源入口。分类记录不提供可食用性保证，也不等于实时更新后的全球分类学共识。

引用：GBIF Secretariat (2023). GBIF Backbone Taxonomy. Checklist dataset. Accessed via the GBIF species API on 2026-10-27.

- [数据集与许可](https://www.gbif.org/dataset/d7dddbf4-2cf0-4f39-9b2a-bb099caae36c)
- [数据集 DOI](https://doi.org/10.15468/39omei)
- [GBIF species API](https://techdocs.gbif.org/en/openapi/v1/species)
- [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)

## Commons 图片

API 返回图像地址、文件说明页、作者、许可与许可链接。默认直接加载远程缩略图；选择后台中转、或远程图片加载失败后自动重试中转时才下载。图像可能经 object-fit 裁切预览，原图入口保留完整画面。

API 可访问、直链可显示与许可条件是不同事情。Commons 多数作品可按各文件许可复用；应核查文件说明页，依要求署名、链接许可，并说明裁切、加字等修改。API 返回元数据不能替代逐图核对。

图库为候选检索结果，未逐张人工鉴定植物和原料形态。以后发布视频时，需把所用图片的作者、文件页、许可与修改记录带入发布材料。

- [Commons 复用说明](https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia)

## 其他网站和搜索

NParks、ICAR、McCormick 等只有少量简短编辑阅读提示与原站链接，不随包复制完整文章。不同条目可以有不同来源，不假定这些站点都有可通用调用的公开 API。

百度百科和图片保留原站入口；Bing 在当前响应允许时可尝试原站 iframe；Google 为原站入口或已有资格的 API。搜索结果不是图片复用授权。来源视窗显示原站内容，仍受原站嵌入与使用规则控制。

- [Bing Search APIs 退役公告](https://learn.microsoft.com/en-us/lifecycle/announcements/bing-search-api-retirement)
- [Google Custom Search JSON API 状态](https://developers.google.com/custom-search/v1/overview)
- [Wikimedia User-Agent 政策](https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy)
- [浏览器 X-Frame-Options](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Frame-Options)

## 字体

网页可从 Google Fonts 加载 Noto Serif SC、Cormorant Garamond、Cinzel、Ma Shan Zheng；本包未重新分发字体文件。离线回退到系统字体。展签是现代排印意象，不是字体年代或香料历史起源的考据结论。

## 翻译服务与项目代码

Google Cloud Translation 与 Azure AI Translator 分别采用其官方服务条款、凭据和计量规则。用户需要自行配置账号、配额和密钥；搜索网页的可访问性不等于翻译 API 已开通。

- <https://docs.cloud.google.com/translate/docs/setup>
- <https://cloud.google.com/products/translate/pricing>
- <https://learn.microsoft.com/en-us/azure/ai-services/translator/text-translation/reference/v3/translate>

此文件说明第三方内容归属，不代替项目源代码的开源许可证。完整作者署名、非营利用途说明与源代码 license 按项目计划后续确定；本版不擅自为用户指定作者身份或开源许可。
