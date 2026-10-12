# Read-only coverage budget preflight

This directory is experimental measurement and dry-run logic, not an activated maintenance system, deployed client adapter, or claim of expanded coverage.

## Approved execution boundary

`coverage-preflight.yml` uses one standard public-repository Ubuntu job, a 10-minute job timeout, and read-only repository permission. It runs only by explicit dispatch or a push to the named test branch. It verifies the existing public bootstrap and writes compact console/Actions-summary results. No source downloads, artifact uploads, dependency installs, cache uploads, paid services, deployment, private-repository dispatch, telemetry, or scheduled execution are included. A future merge touching only this directory and its dedicated workflow does not match the pilot publisher's tool/config push filters.

GitHub documents public standard runners as free and says log files/job summaries do not count toward artifact storage. This does not imply unlimited service capacity or guarantee zero impact on shared infrastructure: https://docs.github.com/en/billing/concepts/product-billing/github-actions .

## Measurements and interpretation

`run_preflight.py` reconstructs the public Chicagoland bootstrap using its existing canonical checksum verification, compares retained zoom levels 8–12, 8–13, and 8–14, then compares 4×4 and 8×8 spatial whole-fetch bundles at high zooms. Native-zoom truncation is only a storage measurement on existing regional data. It does not prove full-state capacity, acceptable overzoomed geometry, memory, or generation runtime.

`tile_bundle.py` validates experimental RTB1 binary packing; `bundle_measure.py` checks every packed tile byte-for-byte and measures cold synthetic viewports. It is not shipped to map clients. Integration would require bounded request concurrency, in-flight deduplication, reference-counted cancellation, a byte-accounted LRU, strict binary validation, occupancy checks, and provider fallback tests. Preserve canonical raw-dataset identity separately from transport format identity.

The current canonical bootstrap version is verified at runtime, not assumed from an earlier deployment's similar tile counts. Timestamp-only metadata must not change raw-data identity.

## Coverage correctness

Expanded requested coverage is an irregular union: Illinois, Wisconsin, Michigan including its Upper Peninsula, Indiana, and explicit nearest-half masks for Iowa, Missouri, and Kentucky. A union bounding box is never sufficient proof of coverage. Publish either a validated polygon/MultiPolygon coverage mask or guaranteed covered cells, identical on primary and mirror hosts. A point in a gap must use the broader fallback; never infer full coverage from an empty tile or a bounding-box match.

The geometry helper here only tests controlled non-antimeridian fixtures: disconnected polygons, a gap inside their combined bounding box, holes, and boundaries. It is not a substitute for validated real state polygons or a robust production geometry library. Actual half-state masks and statewide output remain unmeasured.

## Maintenance preparation

`select_work` is a pure dry-run decision helper. It prioritizes existing regions whose source checks are 75 days old, providing a 15-day lead toward a 90-day target. Unknown freshness demands a source check. Expansion requires an explicit measured maintenance reserve and runtime headroom. Unknown forecasts block growth. It does not record state, call APIs, schedule jobs, or enforce an account billing cap.

Before activation, integrate reliable run-attempt accounting, verified source-check timestamps, durable previous-publication recovery, a kill switch, and fail-closed admission. Budget checks must include failed/manual attempts and setup/deployment jobs. Source checksum verification may advance freshness without rebuilding unchanged tiles; simply rerunning a workflow cannot make stale source data current. Preserve last-known-good coverage on any failure and pause growth when maintenance no longer fits the budget.

## Local tests

Run `PYTHONPATH=preflight python -m unittest discover -s preflight -p 'test_*.py' -v`, then `python preflight/run_preflight.py`. Seventeen focused tests passed locally before the first CI run. CI must be checked separately on its exact remote commit.
