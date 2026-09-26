# Data and feature path consistency audit

Reviewed: 2026-09-22. Scope: the checked-out repository, including setup instructions, Make targets, manual pipeline stages, Dagster, Kaggle notebooks, AWS refresh scripts, database loaders, public API queries, frontend navigation, model artifacts, and review workflows.

This is an audit, not an implementation change. No production database, collection service, deployed application, or private account was accessed. Findings describe executable code paths and defaults; production prevalence requires checking deployed configuration and data.

**Result:** the project does not consistently use the same publication population across its execution paths. Several public features bypass the accepted-AI boundary. Other paths use different eligibility rules, classifiers, review handling, or artifacts.

The intended contract used for this review comes from the root README's Sri Lanka ownership policy, `backend/docs/AI_RELEVANCE_PIPELINE.md`'s AI-before-topic-modeling rule, and `frontend/README.md`'s accepted-AI boundary. Broad candidate data and mixed AI/non-AI training data are valid intermediate inputs. The problem is using them as public final data, or silently dropping required processing stages.

## Path map

| Entry point or feature | Actual source and behavior | Assessment |
|---|---|---|
| Root fresh-clone instructions | Historical `make reset-db-ai` path now delegates to a non-destructive compatibility alias; prefer `make load-db-ai` | Compatibility path |
| Manual database Make targets | `common_publications_final_2016_2026.csv`; no AI classification or review backfill | Broader than public corpus |
| Manual runbook database load | Type/journal-normalized CSV; no AI classification or review backfill | Different branch again |
| EC2 initial deployment | AI-only CSV with DOI requirement; separate review runbook provides backfill | Depends on following both workflows |
| Dagster database asset | Ownership-validated → analysis-ready → AI classification → AI + review → load → review backfill | Most complete integration; differs from other entry points |
| Historical AI-only builder | Old default SVM → AI label + valid DOI → optional reset/load | Drops review candidates; no review backfill |
| CLI / Make / admin incremental update | OpenAlex → classification → AI label + valid DOI → load | No ownership gate or review backfill; settings differ |
| Full monthly EC2 refresh | Generic framework → existing common CSV model inputs → broad CSV reset/load | Does not execute the intended common-data build chain |
| Kaggle monthly deployment | Notebook outputs → broad CSV reset/load | Does not select the Dagster AI/review output |
| Public lists, normal aggregate rankings, quality analytics, exports | Shared SQL `build_where` requires accepted review status | AI acceptance scoped; metadata attached to responses is broader |
| Publication details, researcher/institution profiles, suggestions | Direct SQL against `final_publications` | Acceptance scope bypassed |
| Semantic results | Offline embedding candidates intersected with accepted database rows | Acceptance scoped, but stale/incomplete index can miss records |
| NMF directory and trends | Offline CSV counts, shares, and assignments | Not intersected with current accepted population |
| NMF publication listing | Artifact assignment keys intersected with accepted database list query | Can disagree with NMF directory counts |
| Entity-resolution admin queue | Explicit sample fixtures and frontend JSON decisions | Demonstration workflow; not connected to pipeline merges |

## Findings and correction plan

Priority **P1** means incorrect publication eligibility, loss of durable review state, or a broken main operational path. **P2** means inconsistent results, incomplete processing, or a disconnected feature. Numbers are stable identifiers, not a strict ordering within a priority.

### 1. P1 — Public details and profiles bypass accepted-AI filtering

`backend/src/api/repositories/sql.py:124` applies an accepted-review `EXISTS` clause to list queries. However, `backend/src/api/repositories/postgres.py:263` (`get_publication`), `:302` (`suggest`), `:1528` (`_rows_for_multivalue`), and `:940` (`_researcher_coauthor_rows`) query the base table without it. Metadata at `:189` also counts the broader table. References and count-audit lookups do not verify public eligibility either.

Researcher and institution profiles and their publication lists use `_rows_for_multivalue`. Therefore, a pending or rejected publication absent from search can still appear on a profile or through its direct URL. A filtered directory and a profile reached from that directory can report different totals. The special researcher coauthor query has the same problem.

**Correction:** use one public eligibility query/view for all public reads, including details, profile helpers, suggestions, references, audit evidence, and metadata. Keep broader review access on explicit admin paths. Add a shared acceptance-scope test matrix for every public endpoint family.

### 2. P1 — Incremental loading does not enforce Sri Lanka ownership

The full Dagster chain validates ownership before downstream processing (`backend/dagster-quickstart/src/dagster_quickstart/defs/researchlanka.py:1367`). Incremental selection only checks the AI label and valid DOI (`backend/src/pipeline/incremental_update.py:312`). Ownership fields are computed by the OpenAlex normalizer but not enforced here; strict collection is optional and defaults off.

**Reproduced:** a row with `ownership_decision=EXCLUDE`, an AI label, and a valid DOI is selected for loading. Once its AI review is accepted, the current shared public filter does not independently reject its ownership decision.

**Correction:** apply the same `INCLUDE` + HIGH/MEDIUM confidence + no ownership review rule before public eligibility. Retain noneligible evidence separately. Enforce this invariant at the public boundary as well as in ingestion.

### 3. P1 — Repository append command changes what “final” means

`backend/src/pipeline/add_repository_records_to_final.py:52` explicitly selects ownership `REVIEW` / `REPOSITORY_ONLY_EVIDENCE` rows. The writer at `:82` appends them to `common_publications_final.csv`. `backend/Makefile:327` exposes this operation as `final-common-add-repositories`.

This contradicts the README's definition of that same file as verified ownership-only. It is not an issue with retaining candidate records; it is a candidate workflow mutating the verified output in place.

**Correction:** write these records to the ownership-review/candidate dataset. Require explicit ownership adjudication before promotion to the verified final output.

### 4. P1 — Several loaders omit the review records needed for visibility

Dagster explicitly backfills review rows after loading (`backend/dagster-quickstart/src/dagster_quickstart/defs/researchlanka.py:2025`). `load_record_file`, the historical AI-only builder (`backend/src/pipeline/build_ai_publication_dataset.py:75`), and incremental loading (`backend/src/pipeline/incremental_update.py:421`) do not.

For newly inserted keys, an AI classification alone does not satisfy the public `ai_review_records` join. An incremental run can report success while its new records are missing from accepted lists and the review queue until a separate backfill is executed. Reusing an existing key can instead preserve old review state alongside changed model metadata.

**Correction:** share a transactional ingestion service that upserts publications and creates/updates review workflow records, preserving human decisions under an explicit policy. Report ingested, pending, accepted, and rejected counts separately.

### 5. P1 — Routine reset paths erase review decisions and audit history

`backend/src/database/load_records.py:409` uses `TRUNCATE ... RESTART IDENTITY CASCADE`. Migration `backend/database/migrations/010_create_ai_review_workflow.sql` makes review records, events, and synchronization jobs reference `final_publications`. PostgreSQL's truncate cascade includes these dependent tables.

The monthly scripts invoke reset targets, and the historical builder uses `reset=True`. Rebuilding the publication table therefore clears durable review history and queued synchronization work. Running backfill afterward cannot reconstruct completed human decisions or their audit trail.

**Correction:** use staged, validated upserts and controlled retirement of missing records for routine refreshes. Reserve destructive resets for explicit clean setup; preserve review history by stable publication identity. Current loader safeguards disable `--reset` unless `RESEARCHLANKA_ALLOW_DESTRUCTIVE_RESET=1` is explicitly set, and `--retire-stale` soft-retires missing records instead of deleting them.

### 6. P1 — Monthly refreshes select the broad CSV instead of the AI workflow output

EC2 initial deployment loads `common_publications_final_2016_2026_ai_only.csv` (`docs/aws-ec2-app-deployment.md:96`). Both `scripts/aws_monthly_pipeline.sh:17` and `scripts/aws_trigger_kaggle_monthly.sh:22` instead default `DB_INPUT` to `common_publications_final_2016_2026.csv`, then reset/load it. Dagster produces a different downstream file ending `_ai_review_filtered.csv`.

The broader input may lack AI classification entirely. Combined with findings 1, 4, and 5, a refresh can empty accepted lists while broader detail/profile paths remain readable. These are consequences of the code defaults, not a claim that production has already been refreshed this way.

**Correction:** make all production refreshes consume one declared ingestion artifact and the shared review-aware loader. Fail validation if the artifact lacks required classification, ownership, or version metadata.

### 7. P1 — The full monthly script does not rebuild the files it later consumes

`scripts/aws_monthly_pipeline.sh:55` calls `run_pipeline.py --stage all`. That wrapper runs `research_analytics.ResearchPipeline`, not the Dagster common-dataset build. The configured explicit source is `data/processed/repositories_combined.csv` (`backend/configurations/sri_lanka/config.json:21`); `_configured_sources` selects it (`backend/research_analytics/pipeline.py:419`). `run_all` at `:284` does not run the `build_final_common_dataset` / year / analysis-ready / AI filtering chain.

The monthly script subsequently reads common final/analysis-ready CSVs by name. On a clean system these can be missing; on an existing system they can be stale. The generic framework also has database loading enabled and AI classification disabled in this configuration.

**Correction:** invoke the actual production build graph, then consume output paths and run IDs returned by that graph. Verify that every deployed artifact belongs to the current successful run.

### 8. P1 — NMF can be trained on the full corpus despite the AI-only plan

`backend/docs/AI_RELEVANCE_PIPELINE.md:177` requires AI filtering before topic modeling. But `dse-project.ipynb`, code cell 35 (zero-based JSON cell index), passes `common_publications_final.csv` to NMF. The generic framework defaults to the same broad file at `backend/research_analytics/pipeline.py:388`. `run_final_pipeline` does text cleaning but does not validate AI acceptance.

Executing these documented paths can produce general-research topics presented under an AI-focused frontend.

**Correction:** build production NMF from a versioned accepted-AI snapshot and validate the input contract. Retain broad-corpus experiments under separately named outputs.

### 9. P2 — NMF counts and filters do not match its publication listing

`backend/src/api/repositories/nmf_topics.py:76` loads precomputed counts/shares and counts every artifact assignment. The NMF directory service (`backend/src/api/services/nmf_topics.py:69`) does not apply institution, field, keyword, or year filters even though the public route accepts them and the frontend sends them. Topic publications at `:114` are retrieved through the accepted database list query instead.

**Reproduced:** adding an impossible institution and `year_min=2099` directly to the NMF directory service returns the identical response. Changes in accepted review state can also change the publication list without changing the displayed topic count or trend.

**Correction:** calculate counts/trends from assignments joined to the currently eligible, filtered publication keys, or explicitly expose a fixed historical snapshot and reject unsupported filters. Version assignments with the corpus.

### 10. P2 — NMF generation and serving disagree on directory and topic count

The primary notebook writes `data/processed/common/nmf` and sweeps k=8/10/12 (cell 35). The framework defaults to that directory and k=20 (`backend/research_analytics/pipeline.py:390`). Serving searches `data/processed/common/nmf/k25` or a notebook output directory and hardcodes `self.k = 25` (`backend/src/api/repositories/nmf_topics.py:17`, `:66`).

A successful generation run can leave the API reporting missing artifacts or serving an older k25 directory. Setting an override to another k can still misreport k as 25.

**Correction:** publish a manifest with the artifact directory, k, corpus version, and build version. Resolve serving from that manifest and derive k from the artifact itself.

### 11. P2 — Classification model, text inputs, and thresholds vary by entry point

Dagster classification defaults to `model_selection/best_ai_relevance_model.joblib`, nine text fields, and P(AI) thresholds 0.85/0.40 (`backend/src/pipeline/classify_ai_relevance_dataset.py:18`). Incremental/historical classification defaults to `ai_relevance_linear_svm.joblib`, five text fields, a predicted-label confidence, and an optional confidence cutoff (`backend/src/pipeline/incremental_update.py:42`, `:224`). Make supplies 0.60; direct CLI and the admin job default to no cutoff. Compose explicitly selects the older SVM path. The model-selection document describes a selected logistic regression model and a 0.60 review cutoff.

**Reproduced with the same fake probability model:** P(AI)=0.55 becomes `review` in the Dagster classifier, `AI` in direct incremental classification, and `review` when the Make cutoff is applied. Database backfill adds its own acceptance policy; this does not undo records discarded before loading.

**Correction:** use one versioned inference configuration for model, feature columns, probability meaning, and thresholds. Keep model prediction and human acceptance as separate fields. Broad supervised training data is not itself an inconsistency.

### 12. P2 — Uncertain AI records reach review only on some paths

Dagster keeps both `AI` and `review` labels. Historical/incremental selection defaults to only `AI`; the admin launcher explicitly passes `--db-labels AI` (`backend/src/api/services/incremental_admin.py:64`). The selector also requires valid DOI, whereas the Dagster loader does not add that requirement.

Consequently, uncertain records can be available for human review after a full rebuild but discarded by an incremental refresh. A no-DOI publication can likewise be retained by one path and dropped by another.

**Correction:** separate “eligible for ingestion/review” from “accepted for public display.” Preserve review candidates and decide the DOI requirement once for each layer. Do not put a public AI-only filter in front of the review queue.

### 13. P2 — CLI/cron and the admin UI use different checkpoints

`backend/src/pipeline/incremental_update.py:463` hardcodes CLI defaults to JSON state and key `incremental_update`. Make does not pass a state backend/key. `scripts/aws_incremental_pipeline.sh` logs a database-default backend but calls this Make target. The admin wrapper reads `RESEARCHLANKA_INCREMENTAL_STATE_BACKEND` and `RESEARCHLANKA_INCREMENTAL_STATE_KEY` (`backend/scripts/admin/run_incremental_update_job.py:53`); Compose sets database state and key `openalex_incremental`.

Switching between the admin button and cron can therefore use independent collection positions, despite the configured environment suggesting a shared one.

**Correction:** resolve the same state configuration in the common pipeline entry point and log the resolved backend/key. Pass the same values through every wrapper.

### 14. P1 — Incomplete or collection-only runs advance the ingestion checkpoint

Collection returns early for `max_records` (`backend/src/pipeline/incremental_update.py:174`), but successful return from the pipeline records the requested end date. The `skip_db` branch at `:414` also continues to checkpoint saving. Next collection starts the day after that date (`:89`).

**Reproduced with collection/database operations mocked:** `skip_db=True` advances `last_successful_collection_date` to the requested end date. A capped run can similarly mark an unexhausted interval complete. Later normal ingestion can skip records that were never loaded. Separately, collection is based on publication date, so late-indexed records with older publication dates need an overlap/reconciliation policy.

**Correction:** advance the ingestion checkpoint only after complete interval collection and successful persistence. Keep collection-only and preview state separate; persist cursors for partial runs. Reconcile late-indexed records with an overlapping window or suitable update-based collection strategy.

### 15. P2 — Normalization and author disambiguation are separate branches that loaders skip

Institution normalization reads `common_publications_final.csv`; type/journal normalization and author disambiguation both independently read `common_publications_final_institution_normalized.csv` (`backend/src/pipeline/build_institution_normalized_dataset.py:52`, `build_type_journal_normalized_dataset.py:41`, `build_author_disambiguated_dataset.py:54`). The runbook loads the type/journal branch (`backend/docs/PIPELINE_RUNBOOK.md:468`), which does not incorporate the author-disambiguation output. Make instead loads the earlier year-filtered CSV. Dagster AI classification consumes its analysis-ready branch.

Running all the normalization commands does not mean the application receives all their improvements. Author IDs, standardized venue/type data, and normalized affiliations can differ by deployment procedure.

**Correction:** compose these stages into one explicit chain and make every serving/modeling artifact descend from its output. Validate the required normalized fields in the ingestion manifest.

### 16. P1 — The documented AI setup commands do not exist in the backend

Root `Makefile` now exposes `load-db-ai` for the historical AI dataset load. `reset-db-ai` remains only as a compatibility alias that prints a production-safety warning and delegates to the non-destructive load.

**Current status:** the AI builder module is wired through `make load-db-ai`; `make reset-db-ai` no longer performs a destructive reset. `backend/docs/PIPELINE_RUNBOOK.md` still says all commands run from repository root while its paths (`requirements.txt`, `scripts/...`, `data/...`) are backend-relative in the current layout.

**Correction:** wire the commands to the shared review-aware pipeline, then verify setup with Make dry runs and a clean-directory smoke test. Correct the runbook's working-directory instruction.

### 17. P2 — Newly built embeddings are not promoted to the serving paths

Monthly embedding generation writes timestamped files (`scripts/aws_monthly_pipeline.sh:70`). Root development commands and Compose default to `publication_text_embeddings_cli_sample.parquet` and its matching sample model (`Makefile:19`, `compose.aws.yml:31`). The generic fallback chooses the largest file, not a validated current deployment (`backend/src/modeling/embeddings.py:397`).

Restarting the API does not switch those explicit sample paths. Newly loaded accepted papers can appear in normal search but be unavailable to semantic retrieval; broad/stale embedding candidates can also consume the retrieval candidate limit before database filtering.

**Correction:** build embeddings for the declared serving corpus and atomically promote the matching model/index manifest. Validate coverage of accepted publication keys. Do not choose production artifacts by filename sample defaults or file size.

### 18. P2 — Frontend classification navigation changes filter meaning

The domain/field/subfield table in `frontend/src/app/topics/page.tsx:119` links subfields with `subfield=...` and every other level with `field=...`. Domain labels therefore reach the API's exact `primary_field` filter rather than a domain filter. The current backend filter contract has no domain key. Frontend `extractFilters` also omits backend-supported `researcher`, `nmf_topic`, and `nmf_topic_id` (`frontend/src/services/filters.ts:16`).

Selecting a domain can produce an empty or incorrect publication list. Manually supplied or future frontend links using those omitted parameters silently lose their intended restriction. The page text also describes all topics as OpenAlex classifications, while `/topics` defaults to NMF (`backend/src/api/services/publications.py:433`).

**Correction:** add a real domain filter end to end, align frontend/backend filter contracts, and distinguish OpenAlex taxonomy from NMF topics in the page text.

### 19. P2 — Entity-resolution review is not connected to the production pipeline

`frontend/src/services/workspace/resolution.ts` explicitly sets `SEEDED_FROM_FIXTURE = true`. Merge/reject actions update frontend JSON and an audit entry; they do not invoke pipeline deduplication or update the publication database. This limitation is honestly disclosed in the code/UI, but remains a gap if the implementation plan treats admin entity resolution as complete.

**Correction:** track this as a demonstration feature until candidates and adjudications are connected to durable pipeline inputs. Ensure a “merged” decision is applied on the next build and traceable to the resulting publication identity.

## Recommended implementation order

1. Define separate candidate, ownership-qualified, classified, pending-review, and accepted-public populations. Store a versioned contract for each. Do not use the filename `final` as the only indication of eligibility.
2. Fix public query scope, including details/profiles/coauthors/metadata. Centralize ownership and accepted-review eligibility.
3. Replace production reset/reload with review-preserving ingestion. Wire review creation into every loader and preserve uncertain candidates.
4. Unify full rebuild, historical import, incremental, admin, Kaggle, and AWS entry points around the same graph/configuration. Repair setup targets and checkpoint semantics.
5. Connect all normalization stages. Publish NMF and embeddings through versioned manifests tied to the same accepted snapshot; reconcile live review changes.
6. Align frontend filters, labels, and counts with the backend contract. Explicitly track fixture-backed features and update historical plans/runbooks.

Before calling the paths consistent, test a small shared corpus containing accepted AI, pending AI, rejected AI, non-AI, ownership-excluded, no-DOI, late-indexed, and human-adjudicated records through every entry point. Compare stable publication keys and review states, not just row counts.

## Verification performed

- Read-only Make dry run previously reproduced the missing `reset-db-ai` target; this is now covered by the `load-db-ai` target and non-destructive compatibility alias.
- In-memory SQL capture confirmed that list queries include review acceptance while detail/profile/suggestion/metadata/coauthor queries do not.
- Synthetic records reproduced ownership exclusion bypass, entry-point-dependent classification, and collection-only checkpoint advancement. External collection and persistence were mocked.
- Existing NMF fixture reproduced ignored directory filters.
- Focused existing tests: **93 passed** across `test_ai_review_workflow.py`, `test_incremental_update.py`, `test_classify_ai_relevance_dataset.py`, `test_api_service.py`, `test_nmf_topic_endpoints.py`, `test_load_records_script.py`, and `test_database_loader.py`.
- No live database migration, reset, external harvest, model training, deployment, or outbound message was performed. The passing suite does not establish cross-path consistency; the reproductions above identify coverage gaps.
