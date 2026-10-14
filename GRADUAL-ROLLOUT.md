# Budget-bounded US tile rollout

## Operating contract

`rollout.yml` is the sole publisher. It runs weekly Monday 09:23 UTC or by a fresh manual dispatch. A deliberate commit changing only `config/rollout-request.json` on `main` can also request a run when API workflow dispatch is unavailable; use a nonsecret unique request ID and explain the requested run in the commit. The path itself is the trigger, so never use it for routine edits. Normal source pushes run verification only. All publishing triggers share `ride-tiles-pages` with cancellation disabled.

Do not use GitHub's rerun-failed-jobs button to publish: build and deploy are blocked on attempts greater than one, which prevents reuse of a successful budget gate from a previous attempt. Start a fresh dispatch instead. Historical attempts, failures and retired publisher runs still count in the next budget calculation.

The workflow validates code, queue and recovery fixtures before generating data. It restores the latest publication, attempts overdue existing mutable regions oldest-first, and attempts at most one eligible new city only after all eligible due refreshes are complete. Missing refresh configuration blocks expansion. The initial publication has no refresh ledger, so existing Chicago and NYC are due immediately. Subsequent successful checks target a 90-day interval. Exact Chicago metro is always excluded from regeneration.

A failed or oversized region is recorded with its reason and a 21-day retry date. A failed refresh prevents expansion that same run. Later runs may refresh other regions or add one city while that region is explicitly deferred. Deferred coverage remains visible, marked overdue in the report, and is never claimed current. A failed expansion candidate similarly yields to the next eligible queue entry during backoff. Maintenance metadata may be the only change published to make this backoff durable. Successful unchanged-tile checks also update freshness-check metadata, while preserving the original content-addressed source/provenance. If no due check, eligible addition, or state change exists, no artifact is uploaded and no deployment runs.

A refresh target is not a coverage guarantee. At one successful refresh per week, roughly 13 mutable areas can sustain a 90-day cadence; 50 areas would need about four refreshes per week. Faster builds may fit more existing refreshes into a run, but this code never increases the budget to force that outcome. The manifest is capped at 50 entries and 100,000 bytes for the current app. Because Chicago metro occupies a separate entry, the current client cap stops the 50-city queue before its final city. App-limit changes require a separate reviewed release.

## Runtime and download limits

- 100 elapsed runner minutes per UTC month is the admission threshold for publishing workflows. Every completed job is rounded up individually; failed/cancelled attempts and historical retries count. Cross-month jobs are conservatively charged in full to the later month.
- A gate reserves all job timeouts: budget 2 minutes, build 15 minutes, deploy 5 minutes, total 22. The guard scans unfiltered visible run history so a rerun of an old-created run cannot disappear from a creation-date filter.
- Missing attempts, malformed history, incomplete pagination, API errors/rate limits, competing unfinished publishers and bounded-audit limits deny admission. Public unauthenticated API calls introduce no credential scopes. Their shared-IP rate limit can skip an otherwise affordable run.
- This is not a literal total Actions cap or account-wide billing cap. A rejected gate itself uses runner time, so unlimited manual/gate retries can exceed 100 minutes even though no further build is admitted. Do not repeatedly dispatch a denied run; investigate the report or wait for the next month. Deleted whole runs cannot be reconstructed or reliably detected by the public API; the cap relies on retaining publisher history. Do not delete publisher history during the current month.
- The build job stops after 15 minutes. A shell watchdog interrupts the orchestration process after 540 seconds and kills it after another 10 seconds. Region processes have independent process groups killed after at most 240 seconds, including curl/osmium descendants. The orchestration reserves 90 seconds for final hashing/packaging and starts no region with less than 60 seconds available.
- Rollout source downloads have no curl retries, a 20-second connection timeout, 180-second download timeout, a 1,500,000,000-byte per-file ceiling and a conservative 3,000,000,000-byte cumulative run ledger. Failed transfers keep their full reservation charged. Runtime timeout still bounds processing of statewide extracts. Source-size growth therefore defers a city rather than raising caps or looping.

## Publication and recovery

Every deployment retains all prior region/version files and source archives. The old Chicago `19785f3c1ca31233` and metro `8d555e92cfa68b53` files are checked against the known offline reference; metro's manifest entry also remains exact. New broad-Chicago and NYC builds keep the old bounds, adding Michigan and New Jersey source coverage respectively. Cloudflare's separate regional release is unchanged.

The published `snapshot.json` inventories data-file sizes/hashes and pins a self-contained gzip/tar archive split into shards of at most 8,000,000 bytes. It includes all historical regions, public source extracts, manifest and refresh/backoff state. Old recovery shards are replaced, never recursively archived. Restoration validates both each shard and the entire archive, every extracted path/file, current region tile hashes/version/count/bytes, source hashes/provenance, local URLs, frozen references and the exact live manifest. Only fully validated staging is made available for upload.

On the first run only, descriptor HTTP 404 permits the checked-in bootstrap. The complete live manifest, ignoring only root update timestamp and region order, must match that known snapshot. Unknown live coverage makes bootstrap fail closed rather than silently dropping it. Other HTTP errors, corrupt descriptors and corrupt archives never fall back. Immediately before upload and again before deployment, the live manifest must still match the restored starting hash. The shared publishing concurrency handles normal workflow races; the late check also detects outside publishers, though no client-side check is a server-side compare-and-swap.

Full published bytes, including recovery shards, historical version directories and ODbL source downloads, must be at most 250,000,000 bytes. Every file is limited to 24,000,000 bytes, conservatively below 25 MiB. Over-limit candidates are discarded without dropping old coverage. The current repository's unexpired Actions artifacts plus a conservative new artifact estimate must also fit 250 MB before upload. No artifacts are deleted, and no caches or duplicate review artifacts are created. The Pages artifact retention is one day.

Standard public-repository runners are free under GitHub's current public-runner policy, but artifact storage is account-shared and usage in other repositories is unknown. These repository-level bounds do not guarantee the account will never incur charges. GitHub Pages also has platform-wide limits, including a 1 GB published-site maximum and a 100 GB/month soft bandwidth limit; this rollout does not measure traffic or implement usage-driven expansion.

## Verification and reports

Run both suites with dependencies from `requirements-dev.txt`:

    python -m unittest discover -s tests -v
    python -m unittest discover -s publishing/tests -v

`rollout-report.json`, stdout and the Actions step summary report changed coverage, refreshed regions, deferred reasons, due backlog, addition and total site bytes. They remain job output, not a separately retained artifact. Phase/region messages are flushed before each build and sealing operation so interrupted runs remain diagnosable. A workflow failure cannot deploy partial staging. If storage/accounting denies admission or publication, the previous live site remains authoritative.

Primary platform references: [Actions public-runner billing](https://docs.github.com/en/billing/managing-billing-for-your-products/managing-billing-for-github-actions/about-billing-for-github-actions), [Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits), [public workflow run reads](https://docs.github.com/en/rest/actions/workflow-runs#list-workflow-runs-for-a-repository), [attempt-specific job reads](https://docs.github.com/en/rest/actions/workflow-jobs#list-jobs-for-a-workflow-run-attempt), [artifact API](https://docs.github.com/en/rest/actions/artifacts#list-artifacts-for-a-repository).
