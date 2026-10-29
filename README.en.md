# Spice Atlas

English · [简体中文](README.zh-CN.md) · [Release history](CHANGELOG.md)

A local botanical reading desk for exploring herbs, spices and their sources. Search a catalogue stored on your computer, open live encyclopedia articles and ingredient images, and keep the references beside what you read. Material colours, quiet typography and botanical transitions give each ingredient its own atmosphere.

**Local-first catalogue · live references · bilingual reading**

The public repository contains the application source. Run the Python service on your own computer; the repository is not a hosted copy of the application. The current feature set is described in the [release history](CHANGELOG.md).

## Start locally

Python **3.11 or newer** is required. The first dependency installation and new online content require internet access.

**Windows:** extract the complete release into a writable folder and double-click `run.cmd`. A window shows startup stages while dependency installation and the server run without a persistent console. The page opens only after its local API is ready. The tray icon then lets you reopen the page, view startup status/logs, or choose **Stop service & exit**. Closing the progress window hides it; it does not stop the service. If the tray is unavailable, the status window remains available. The native launcher requires Python with **Tcl/Tk**; `run_console.cmd` provides the visible-console fallback.

The progress percentage represents completed stages, not a download measurement: package checks begin at 30%, server readiness waits at 90%, and the browser opens after readiness. Startup logs are in `data/launcher/logs/`. A second launch from the same folder reopens the running instance. When port 8765 is occupied, the launcher can use a nearby free port and opens its actual address. The Windows tray and progress UI still require validation on a Windows device; the automated lifecycle tests run separately.

**macOS / Linux:** run `sh run.sh` in the extracted folder. Keep the terminal open; Ctrl+C stops the service. The default local address is <http://127.0.0.1:8765>.

| Setup | Commands |
| --- | --- |
| With uv | `uv sync --frozen`, then `uv run python launch.py` |
| With pip | Create a virtual environment, install `requirements.txt`, then run `python launch.py` from that environment |
| Alternate port | `python launch.py --port 8766` |

Use the local HTTP address. Opening HTML directly cannot connect to the Python API. Node.js is optional and used only for developer checks and the synthetic preview.

Extract upgrades into a **new folder** and keep the old folder as a backup. Avoid overwriting the new cleaned baseline with an older database. On first initialization, an optional root `config.local.json` is migrated into the initial workspace; an existing workspace registry takes precedence. Personal configuration and workspace data are excluded from release packages.

The Git checkout stores the baseline as `data/catalogue.sqlite3.gz`. First launch verifies its size and SHA-256 before restoring SQLite. Existing databases are preserved. Portable ZIP releases contain the plain baseline and require no manual decompression.

## Explore the collection

1. Choose **Auto, Simplified Chinese, Traditional Chinese or English** in the header.
2. Search names, scientific names or recorded aliases in the left catalogue. Typing queries only the local database.
3. Select a record to fetch its article and automatically query Wikimedia Commons. Source links, citations, authors and file licences remain accessible.
4. Switch material forms, such as fresh leaves and dried flakes. The independent image filter also supports powder, seeds, bark, buds, roots, slices, jars and bags.
5. Use **Back / Forward** to revisit reading states, or **Surprise me** to discover another local record.
6. Open the **Aa** edge tab to adjust article typography independently. Click outside or Done to save and close.

The desktop catalogue and reading pane scroll independently. Narrow screens use ordinary page scrolling. The image toolbar groups its heading and form filter on the left, and source choices and external links on the right, with space between them.

### Reading comfort and motion

Article size ranges from 14–28 px, with quick presets, adjustable line spacing and serif, sans-serif or Kai-style typefaces. Available fonts depend on the operating system. Interface text keeps its own size.

| Level | Behaviour |
| --- | --- |
| 0 · Still | No application animation or smooth scrolling |
| 1 · Minimal | Short feedback and simple fades |
| 2 · Refined | Reading transitions, sliding drawer and theme reveal |
| 3 · Botanical | Thumbnail-aware popups, directional image changes, layered colour washes, staggered lists and animated reordering |

System reduced motion overrides all levels. CSS and native browser animations avoid a fixed frame timer. Actual frame rate depends on the display, browser and device; 120 Hz playback has not been measured here. Browsers without View Transitions retain a working theme switch and supported fallback effects.

### Pronunciation

English common names show sourced IPA when returned by **Free Dictionary API / Wiktionary**. Playback first uses a recording explicitly marked UK / GB. Otherwise, browser **Web Speech** requests `en-GB` and prefers an installed British voice. If none is installed, the interface explains that the available accent depends on system voices. No user API key is required.

Missing IPA is not invented, and Latin scientific names are not synthesized. Mandarin pinyin is generated locally by **pypinyin**, labelled automatic, and may need checking for polyphonic characters or proper names. Dictionary/audio links retain sources and supplied licensing information. Audio is not bundled.

### Navigation and startup

The floating navigation bar stays at the upper left of the reading pane while the article scrolls. **Back / Forward** remembers up to **60 reading states** in the current tab, separately for each workspace: record, material form, source, image filter, catalogue query/position, reading mode and scroll positions. After going back, a new reading action discards the forward branch. These controls do not undo settings, favourites or database edits.

Settings → Reading & language lets startup continue the last reading, always open **Basil**, or select a random local record. A fresh workspace starts with Basil. Explicit entry URLs and a service-change reload continuation take priority. Random exploration defaults to culinary candidates, excludes the current record, and can optionally include botanical references, which are not evidence of edibility.

### Keyboard shortcuts

| Key | Action |
| --- | --- |
| **R** · Repeat | Repeat the last eligible action against the current state, such as the next catalogue page |
| **N / P** · Next / Previous | Turn the current local catalogue page |
| **Alt + ← / →** | Back / Forward through reading states |
| **Esc** | Close the active popup; return an expanded source window inline |
| **/** | Focus local search |
| **← / →** in the image viewer | Previous / next image |
| **?** | Open the shortcut reference |

The floating **R** control names the repeatable action. At list boundaries it stops; repeated requests during loading are coalesced. Single-letter commands do not fire in input fields, selects, editable text or IME composition, and commands stay within the active popup. Keys typed inside an external source window belong to that source. Esc closes a surface; it does not undo a database change.

## Languages and source order

Interface language, preferred article language and translation target are separate settings.

| Interface mode | Preferred-language sources |
| --- | --- |
| **Only Auto**, when the browser resolves to Simplified Chinese | Baidu Baike → Bing China → other resources, including available Wikipedia |
| Auto English / Traditional Chinese; every manual language mode | Matching Wikipedia → Bing International → Google → other resources |

The other language follows afterwards. Manual Simplified Chinese uses the international order. Missing Chinese Wikipedia can fall back to English; connection failure is distinguished from a missing article.

Wikipedia supports live API articles, focus/full views, outlines, citations and source hyperlinks. Other sites may offer an original-site link rather than embedded text. Name-label typography is a modern design treatment, not historical evidence.

## Live images and source windows

On record or form selection, the browser automatically queries the official **Commons CORS API**, with the backend as fallback. Images normally use remote thumbnails. A failed image URL gets one backend-delivery attempt. The release bundles no photo snapshots.

The 12-profile image vocabulary is based on 39 recorded Commons searches across 30 representative materials and 326 returned filenames. Results are candidates, not verified identifications. Packaging queries affect images only. Empty results are preserved rather than replaced with unrelated forms.

The source window defaults to **Responsive width**: its iframe uses the actual available container width at scale 1. **Scaled preview** is an optional overview based on the browser viewport width. **Expand window** opens the same iframe across almost the entire browser viewport; Return inline or Esc restores it without replacing the iframe, so source inputs and scroll state are retained. Container and browser changes recalculate the dimensions. Cross-origin page layout and embedding permissions remain controlled by the source; some pages keep their own minimum width or prohibit embedding.

Images retain file pages, authors, original URLs and supplied licences. API access, search results and hotlinking do not grant reuse rights. Verify individual permissions before producing a video. See [content and dependency notices](CONTENT_LICENSES.md).

## Translation

Settings → Translation services supports:

- Local **LM Studio / OpenAI-compatible** chat API. Default: `http://127.0.0.1:1234/v1`. Start the server and test `/models`; translation uses `/chat/completions`.
- Official **Google Cloud Translation Basic v2**, with your key and quota.
- Official **Azure AI Translator v3**, with your key, region and quota.

Automatic translation covers up to **eight suitable focus paragraphs**, preserving link markers and checking numbers. Original, translation and bilingual views are available. Multiple source languages can be excluded. Full-article batch translation is not implemented; model output requires review.

Keys are write-only through the settings API and saved in the selected workspace. Blank fields retain saved credentials; explicit clear controls remove them. Copying a workspace copies its settings and keys. Environment overrides are shown separately. Do not share personal workspace folders.

Configured cloud diagnostics send a small Parsley sample and can count toward usage. Unconfigured translation services are not probed. A remote container’s localhost is not your computer’s LM Studio.

Official references: [LM Studio](https://lmstudio.ai/docs/developer), [Google setup](https://docs.cloud.google.com/translate/docs/setup), [Azure Translator](https://learn.microsoft.com/en-us/azure/ai-services/translator/text-translation/reference/v3/translate).

## Connection checks

Sources start **enabled**. Only after the first complete background check are failed services temporarily disabled and their buttons hidden. The default sample is **Parsley**; specialist sites without a mapping use recorded representative pages. Dictionary pronunciation is also checked.

All services, including failed ones, are rechecked every **600 seconds**. Healthy checks are silent. Change notices appear at the upper right and remain until manually dismissed. Later layout changes wait for the next content action, save safe reading state, reload globally and complete that action.

Browser and backend routes are assessed separately. HTTP failure, missing pages and framing restrictions are different conditions. A temporary 403, 429 or 5xx is not proof of permanent unavailability. Detailed diagnostics and manual retesting live in Settings.

## Catalogue, imports and data quality

The cleaned baseline contains **18,379 records**, not 18,379 confirmed edible spices:

| Records | Count | Meaning |
| --- | ---: | --- |
| Culinary material/mixture candidates | 92 | Includes 13 curated examples; others need individual verification |
| Botanical references | 18,287 | Taxa, cultivars or names; culinary use is not confirmed |
| Excluded | 392 | Companies, brands, people, events, utensils, dishes and other mismatches |
| Pending review | 101 | Insufficient/conflicting identity or use evidence |
| Exact-identity merges | 206 | Shared identity or exact scientific name, with archived input |

JDB Group, masala dabba and other unsuitable records are removed from search. The 699 archived decisions retain reasons, original payloads and evidence. Unknown future imports go to review. Simplified / Traditional Chinese search is normalized; bounded English spelling matching supplements indexed lookup. Related records explain known family relationships, not flavour equivalence or substitution.

The source catalogue cutoff is **2026-10-27T04:34:04Z**; entity evidence and cleaning were obtained on **2026-10-28**. This does not mean all world knowledge is current to those dates. Metadata is visible in Settings → Catalogue imports / About.

**Subcategory depth 2** reads the starting Wikipedia category, children and grandchildren. It is category-link depth, not botanical rank. **Category budget 200** limits processed categories, not ingredient records. The queue and pagination cursor are saved; increase the budget and Resume. Information buttons explain both controls.

Imports synchronize identity, names, aliases, classification and mappings; bodies and images stay on demand. The initial GBIF scope uses three specified Backbone families. Use one application process and avoid simultaneous CLI/UI imports into a workspace. Details are in the [Chinese development guide](development.md).

## Workspaces, saved lists and logs

Named **versions** are independent, editable workspaces. Copy one or create from the built-in baseline/defaults; switch, rename, reorder, delete and restore it. Each contains its catalogue, settings, cache, image vocabulary, favourites, history, reading state and log. The manager registry/log sit outside individual workspaces.

Drag handles or arrows persist ordering. Copying/switching pauses imports and retains resumable cursors. Async requests stay with their originating workspace; stale tabs cannot write into a new active one. Deleted workspaces are recoverable. To freeze a state, copy/name it and keep working in another copy. Back up the data folder with the service stopped.

## Documentation and validation

- [Release history](CHANGELOG.md) · [Chinese release history](CHANGELOG.zh-CN.md)
- [Chinese developer and acceptance guide](development.md)
- [Chinese interaction and animation design](docs/MOTION_DESIGN.zh-CN.md)
- [Chinese decision / conversation log](docs/CONVERSATIONS.zh-CN.md)
- [Content, audio and dependency notices](CONTENT_LICENSES.md)
- [Historical design and development notes](docs/history/)

Backend regression: `uv run python -m unittest discover -s tests -q`. Optional UI checks: `npm ci && npm run test:ui`. `npm run dev` starts a clearly labelled **synthetic QA preview**, not the Python application. Current evidence: `data/verification_v06.json`. Earlier evidence and live observations retain their original versioned filenames.

Native Windows UI, personal LM Studio/Google/Azure credentials and target-device audio were not exercised in the Linux test environment. Installed voice packs, audible British output, 120 Hz performance and third-party framing must be checked on the target device. Full-article translation, verified culinary facts for every plant, video production, a full author/licence page and GitHub updating remain future work. **No source-code licence has been selected**; public visibility alone does not grant an open-source licence. Third-party content keeps its own applicable terms.
