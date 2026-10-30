# Supplemental provider research A

Research date: 2026-10-29T05:18:52.798Z. Scope: the 62 sample entries with `sample_index % 3 == 0`. All 62 were queried and completed; 62 initial queries plus 9 entry follow-ups produced 137 selected result links. These are **supplemental search-service results**, not claimed Google, international Bing, or Bing China first pages. Selection is based on returned metadata; it does not certify every page's availability or botanical identity. No article bodies are included.

## Reusable access routes

| Provider | Reusable route and purpose | Access constraints and evidence |
| --- | --- | --- |
| Kew POWO | Resolve a verified IPNI LSID to the observed taxon HTML URL. Kew's own `pykew` repository documents `powo.search`, filters, and `powo.lookup`; distribution is an optional include. | The official client is a candidate integration, not a successful endpoint test in this task. Direct search-service opens of POWO About and Cite Us returned 403. Cache names/IDs and fall back to links or the WCVP names backbone rather than promising live article extraction. |
| IPNI | Verified name records use `/n/{id}`; the official About page documents `/rdf` on record URLs and a Names Reconciliation Service. Useful for nomenclature and authorship. | About currently says no public API while the Kew-owned client describes an HTTP service. Treat this as an unresolved documentation mismatch; verify support before building around internal JSON endpoints. RDF is an explicitly documented route. IPNI records do not establish accepted taxonomy or edibility. |
| MNHN collections | Observed exact-name HTML route: `/taxon/species/{genus}/{epithet}`; specimen record URLs supply types and collection evidence. Search form has scientific-name and type-status fields. | This is an HTML resolver pattern inferred from observed records, not a verified public API contract. The search form opened successfully. No primary documentation for a general science.mnhn.fr JSON API was verified. Preserve specimen IDs and original URLs; avoid session/list-position parameters as identity. |
| PlantNET NSW Flora | Observed query structure supports `NSWfl.pl?lvl=sp&name=Genus~species&page=nswfl`; genus pages use `lvl=gn`. | Regional flora scope. Query results must be verified rather than treating constructed URLs as found sources. No public API contract or blanket reuse licence verified here. |
| eFloras / Flora of China | Discover the numeric taxon ID, then link to `florataxon.aspx?flora_id=2&taxon_id={id}`. Flora ID 3 is Chinese Plant Names, a different dataset. | Numeric identifiers must be resolved, not guessed. Useful for morphology and taxonomic notes; preserve the stated flora scope, publication date, and historical-name cautions. No API contract verified here. |
| NParks Flora & Fauna Web | Search-resolve the species to the observed numeric flora page URL; profiles often include cultivation and ethnobotanical headings. | Numeric pages cannot safely be generated from names. No public API or blanket licence verified. Metadata discovery alone does not validate every usage claim. |
| University extension, ICAR-IISR, Spices Board | Search-resolve knowledge pages and official PDFs; examples cover cumin, celery, thyme, black garlic, and chipotle. | Prefer these primary institutional introductions over stores. No common API contract was found. Keep article links and concise original annotations instead of copying texts. Culinary blends may need editorial sources because they are not plant taxa. |

## Primary documentation

- [Kew-owned pykew client and usage documentation](https://github.com/RBGKew/pykew): search and ID lookup examples for POWO/IPNI. Approximately 39 repository commits were displayed; maintenance recency was not established.
- [IPNI About](https://www.ipni.org/about): public API status, reconciliation service, RDF record access, scope, and registration distinction.
- [Kew Science terms of use](https://www.kew.org/science/collections-and-resources/data-and-digital/terms-of-use): dataset-specific licences, attribution, separate image restrictions, non-endorsement, quality qualification, and variable traffic limits. No fixed requests-per-second limit is published there.
- [POWO contact](https://powo.science.kew.org/contact): names/distribution use WCVP and corrections flow through contributing datasets.
- [POWO citation guidance](https://powo.science.kew.org/cite-us): search result points to WCVP bulk data; the direct open was 403 in this run.
- [MNHN collections search form](https://science.mnhn.fr/institution/mnhn/search/form?lang=en_US): visible scientific-name, type-status, and collection fields.

Provider investigation added 3 search queries and 9 open/click attempts beyond the 71 entry queries. Three opens were blocked with 403: POWO About, POWO Cite Us, and TAXREF About. TAXREF is a distinct regional reference system and was not treated as a general MNHN collection API.

## Identity and coverage review

- `Mentha lithuanica`: exact binomial not resolved. Kew MPNS returns related infraspecific names containing `lithuanica`; no synonym equivalence was inferred.
- `Salvia rufida`: no exact primary treatment returned. Similar `Salvia rufula` results were excluded.
- `Nepeta exicola`: a GBIF-derived plant-name listing contains the string, but no species-specific primary treatment returned. Do not silently substitute `Nepeta oxicola`.
- `Heracleum barmanicum`: iPlant's historical Chinese flora uses that spelling. Flora of China explicitly discusses the Chinese records under `H. kingdonii`; this is a regional record interpretation, not an automatic global synonym replacement.
- `Vitex divaricata` and `Clerodendrum nutans`: author-qualified alternatives appeared. Keep authorship during matching.
- `Vitex golungensis`: regional-flora/SANBI synonym treatment differs from a provisional World Plants status; flag for taxonomy review.
- Some WFO results contain session parameters, and a few results target stage/test subdomains. Only the returned original URLs were recorded; permanent URLs require later verification.
- `Advieh` and `masala` have weaker institutional introductory coverage. `kala namak` is a mineral salt; black garlic, chipotle, and amchoor are processed products. These must not be modeled as separate plant species.
