# Release history

English · [简体中文](CHANGELOG.zh-CN.md)

Changes use **Added**, **Changed** and **Fixed**, followed by validation and limitations. Historical 0.1–0.3 entries were reconstructed from the saved design brief and archived release notes. They do not imply that Git tags or commits existed then.

## 0.6.0 — Unreleased

### Added

- Windows windowed bootstrap with real stage milestones, hidden child processes, startup logs, project icon and tray controls to open, inspect or stop the owned local service. The visible-console launcher remains available.
- A fixed reading navigation bar, discoverable shortcut reference, and context-aware repeat commands: R, N/P, Alt+arrows, Esc, / and image-viewer arrows. Typing and IME composition are protected.
- A complete interaction/motion inventory, shared popup entry/exit lifecycle, image paging, focus return, animated details, notifications and stable-ID list reordering. Level 0 and system reduced motion remain authoritative.
- Complete standalone English and Chinese guides; the default GitHub homepage includes English first, then Chinese. A small composition script keeps them synchronized.

### Changed

- Source windows use their actual container width by default. Optional scaled preview uses the browser width; expanded view occupies the browser viewport while keeping the same iframe and its input state.
- Settings keep a stable outer frame and scroll individual sections. Reading-history persistence is debounced during scrolling.

### Fixed

- English scientific labels no longer show the Chinese genus annotations in Thyme, Cinnamon and Paprika. Original scientific metadata and identifiers are preserved.
- Modal exits finish before closing and returning focus. Rapid reopening and disabling motion cancel obsolete effects safely.
- Managed shutdown verifies the launch instance and a per-instance secret; a second launch does not stop a service it did not start.

Validation and concrete environment limits are recorded in `data/verification_v06.json`. Native Windows progress/tray behaviour and 120 Hz rendering still need target-device validation. This entry describes a local candidate, not a published Git tag or GitHub Release.

## 0.5.0 — 2026-10-29 · Local review milestone

### Added

- Article typography drawer: independent size, spacing and typeface, preview, outside-click / Escape save, per-workspace persistence.
- Four motion levels, system reduced-motion support, native theme reveal and botanical colour washes with browser fallback.
- Sourced English common-name IPA and UK audio via Free Dictionary API / Wiktionary; browser en-GB speech fallback; labelled automatic local Mandarin pinyin.
- Local random exploration and resume / fixed Basil / random startup settings.
- Up to 60 operation-level Back / Forward states per tab/workspace, including source, form, image filter, catalogue and position. New actions prune the forward branch.
- Separate English / Chinese homepages, histories and third-party notices; Chinese development and decision records.

### Changed

- Image heading and form filter on the left; provider controls and external links on the right, with space between.
- More usable article width and wrapping, preserving independent scrolling.
- Embedded search pages fit the container and recalculate on resize, with native-size mode available.

### Fixed

- Partial startup checks no longer disable sources before the complete first pass.
- View persistence includes the independent image profile and source-window state.
- Navigation survives deferred service-layout reloads and completes the requested operation.
- Section jumps survive late article loading; manual scrolling cancels that pending positioning.

Validation: backend regression, two DOM suites and desktop browser checks; final evidence in `data/verification_v05.json`. Live dictionary observations are separate. Personal translation credentials, audible output on the user’s device and 120 Hz performance are not claimed as verified. The archived ZIP is a local review milestone; it does not imply a Git tag or published release.

## 0.4.0 — 2026-10-28

### Added

- Simplified / Traditional Chinese UI and normalized search; explicit automatic-versus-manual source ordering.
- Background checks every ten minutes, persistent change notices and deferred layout reloads.
- Independent workspace catalogue, settings, caches, image vocabulary, favourites, history and logs; recovery and remembered ordering.
- Official Google / Azure translation adapters, write-only keys and excluded languages.
- A 12-profile image vocabulary informed by 39 searches across 30 materials.

### Fixed

- Cleaned 19,078 inputs into 18,379 admitted records, with 699 exclusion, review or merge decisions archived. Removed JDB Group and other mismatches.
- Separated desktop scrolling and aligned header controls.
- Automatic browser Commons queries with backend and image recovery paths.

Original validation: 87 backend tests and 15 DOM checks, plus desktop/live observations. The later GitHub import added validated gzip seed restoration and five more tests. Automatic GitHub updating stayed deferred. See `docs/history/development_v0.4.zh-CN.md`.

## 0.3.0 — 2026-10-27

### Added

- SQLite catalogue/aliases, classification graph, pagination, Chinese/English lookup and bounded spelling matching.
- Resumable Wikipedia-category and GBIF-family imports: 19,078 source records and 815 category nodes at that stage.
- Web configuration for local translation, language, networking and diagnostics; separate browser CORS/backend paths.

### Changed and fixed

- Expanded beyond 13 fixed records, keeping catalogue metadata local and bodies/images on demand.
- Separated interface/source/translation languages; made keys write-only.
- Distinguished failed connections from absent pages, retained cache on refresh failure, and saved category queues/cursors.

Validation: 48 backend tests, DOM behaviour checks and live metadata. Imported plant counts were references, not verified edible species. See `docs/history/development_v0.3.zh-CN.md`.

## 0.2.0 — 2026-10-27

### Added

- First preserved runnable Python/FastAPI release: 13 records, material forms, botanical colour themes and four name-label treatments.
- Wikipedia Action API articles, focus/full views, outlines, fixed revisions and preserved links/citations.
- Commons metadata, author/licence/file links; existing-customer Google image adapter; external Baidu/Bing and specialist links.
- SQLite cache and fetched snapshots; optional LM Studio focus translation, bilingual reading, JSON export and browser print/PDF.

### Changed

- Connected the approved visual direction to traceable sources, distinguishing links from embedded text.

The archive records backend/syntax validation and a real fetch manifest. This release bundled article/image snapshots and thumbnails; later versions moved toward live delivery. Web-based model configuration was not implemented yet. See `docs/history/development_v0.2.zh-CN.md`.

## 0.1 — 2026-10-27 · Design foundation, retrospective

### Added

- A phased brief for a local herb/spice encyclopedia and later video-material workflow.
- Separate plant identity, ingredient part, processing form and packaging concepts; source, translation and attribution fields.
- A botanical atlas direction: leaf, seed, red-fruit and bark palettes, with modern Chinese/book/inscription typography studies.

The surviving v0.1 document explicitly describes proposals and unverified examples. It **does not establish that a working crawler, translation API or complete website existed then**. The first runnable archive available here is v0.2. See `docs/history/PROJECT_BRIEF_v0.1.zh-CN.md`.
