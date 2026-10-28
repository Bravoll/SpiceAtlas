# Catalogue curation evidence (v0.4)

This is a reproducible classification audit, not a food-safety assessment.

The intake was the v0.3 catalogue: 1,239 culinary candidates (including 13 curated records) and 17,839 GBIF species references. Category membership alone was **not** accepted as proof of culinary identity. Wikidata labels, descriptions, P31 entity types, P225 taxon names, P18 images and Wikipedia language links were fetched from the official APIs on 28 October 2026. Twenty-two missing identifiers were resolved through actual Wikipedia redirects; 1,222 unique Wikidata entities and 175 type definitions were examined. For 175 initially uncertain records, Wikipedia introductory extracts were obtained as additional evidence.

The source catalogue cutoff is 2026-10-27T04:34:04Z. This is the time of the latest imported catalogue record, not a claim that all world knowledge is current to that date. Evidence retrieval and the cleaning operation have their own timestamps.

`cleaned_catalogue.sqlite3` is an independent proposed replacement. The original `data/catalogue.sqlite3` was not modified by this task. Retained entries, aliases, FTS records and memberships were rebuilt together. Excluded, uncertain and merged records remain in the `quarantine` table with the original payload, decision reason and evidence pointers. No source article body or photograph has been bundled into the normal application cache.

The 13 reviewed starter records preserve the original forms, names and scope notes in `data/catalog.json`. In particular, thyme/百里香 and cinnamon/肉桂 retain warnings about differing source scopes, clove remains distinct from lilac, and paprika composition is not assumed uniform. General plant or cultivar references do not receive invented edible forms.

Exact Wikidata identity and exact normalized scientific names were used for duplicate merging. Curated records take priority, followed by existing accepted GBIF records. No fuzzy name matching was used to merge taxa. Ordinary-language similarity is not evidence that two taxa are interchangeable.

`cleaning_report.json` records final counts. `cleaning_decisions.json` gives a row-level audit. `entity_type_rules.json` supplies conservative, finite type rules for future imports; unknown entity types must stay in review. Manual decisions document cases such as JDB Group, masala dabba, actual spice blends, plant cultivars and conflicting aromatic-wood uses.

The full sampled responses are retained in `raw/` for reproducibility. Wikidata metadata is CC0; Wikipedia text remains subject to the original page's CC BY-SA terms and attribution/history. Wikipedia extracts are research evidence, not verified encyclopedic prose authored by this project. GBIF metadata retains its original dataset/source links in each record. The file `pending_extracts.json` is evidence only and is not intended for direct display as new project content.

To reproduce:

```text
uv run python data/research_curation/curate_catalogue.py fetch
uv run python data/research_curation/fetch_pending.py
uv run python data/research_curation/curate_catalogue.py clean
```

The first command checkpoints each API batch and reuses completed batches. Rebuilding against newer evidence requires a separately named evidence directory so that old timestamps remain meaningful.

## Release packaging note

The final release contains the cleaned database at `data/catalogue.sqlite3`, audit decisions, Wikidata CC0 responses, and `pending_source_index.json`. Wikipedia introduction text and its raw extract response files are excluded from the release; consult the indexed original page and history. Full reproduction of the original counts requires the original v0.3 intake database; the shipped baseline is already cleaned. The research scripts are not the daily incremental import path.
