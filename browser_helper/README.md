# Optional native split-view helper

This unpacked Manifest V3 extension lets the local Atlas request a native split with an approved image-search page. A normal web page cannot call the extension Tabs API. Chrome documents `splitWithTabId` and `createSplit` for Chrome 155+; other Chromium browsers are accepted only when the real API exists.

After upgrading, optionally open your browser's extension management page, enable developer mode and choose **Load unpacked** for the **installed Atlas folder's `browser_helper` directory**. Keep this path fixed. Reload Atlas afterwards. The package does not install or enable it automatically. Managed browser policies may prevent unpacked extensions or native split views.

The helper matches only local `127.0.0.1` and `localhost` Atlas pages, requires a recent real pointer/key action, and navigates only approved Google, Bing or Baidu image-search paths. It requests `storage` for its own paired-tab IDs. It does not read remote page contents, modify security headers, bypass verification, or replace an unrelated split view. Original-site login or verification remains the user's action in that independent site.

Without it, Atlas retains source links and manual split instructions. A browser version string alone is never treated as proof of native API availability. Native installation is not part of the automated QA; API lifecycle is tested with a browser-API fixture.

References: [Chrome Tabs API](https://developer.chrome.com/docs/extensions/reference/api/tabs), [Edge split-screen policy](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-policies/SplitScreenEnabled).

## 中文说明

可选安装位置：**已升级的旧图鉴目录内的 `browser_helper`**。在 Chrome／Edge 扩展管理页打开开发者模式，选择“加载已解压的扩展程序”，再刷新图鉴。不要把扩展引用到随后会删除的临时下载目录。本轮没有替用户安装。

实际接口可用时，无法内嵌的来源会在图鉴旁建立原生分屏，随后复用助手自己建立的分屏。旧版浏览器、受管理策略或没有该接口的 Edge 不会被假称支持；仍可新标签页打开，再从浏览器菜单手动分屏。它不会操作非本助手创建的用户分屏，也不会读取 Google／百度页面内容或自动解验证。
