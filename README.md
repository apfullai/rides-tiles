# Ride public cycling tiles

A budget-bounded, gradually expanding GitHub Pages pilot serving public OpenStreetMap cycling-infrastructure tiles for a personal, noncommercial map. This repository contains only standalone tile-generation code, configuration, documentation and public map data. It does not contain Ride application source or anyone's private routes.

The pilot includes an exact Chicagoland mirror (bounds -89, 41.05, -86.65, 43.25; content version `19785f3c1ca31233`) plus a compact New York City rectangle: west -74.05, south 40.65, east -73.85, north 40.90, at zooms 8–14. Coverage is not nationwide. Only the published `manifest.json` declares usable coverage, and a failed build must not replace the previous successful deployment.

## Data and attribution

© [OpenStreetMap contributors](https://www.openstreetmap.org/copyright). Public OSM data and derived databases are licensed under the [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/). Each published region includes provenance, source SHA-256 hashes, replication timestamps, tile hashes and a generation report. New regions include the filtered public OSM source extract; the Chicagoland mirror includes its entire public tile database archive and upstream-source provenance. Preserve attribution when displaying the map. This data is indicative infrastructure tagging, not a guarantee of legal access, safety, or current conditions.

Standalone code is MIT-licensed; this does not relicense the OSM data.

## Gradual rollout and refresh

The authoritative publisher is `.github/workflows/rollout.yml`: weekly Monday at 09:23 UTC, manual dispatch, or an explicit change to `config/rollout-request.json` on `main`. Ordinary source-code pushes do not publish. The two legacy manual publishers are retired to prevent rollback to an older snapshot.

Each admitted run restores the latest live site, refreshes eligible overdue coverage first, then attempts at most one new city. The initial run refreshes all existing mutable regions first. Later refreshes target 90 days, oldest first, only as time and storage permit. Failed builds are deferred for 21 days, preserve current coverage, and are reported; a failed refresh blocks expansion in that run. See [the operating guide](GRADUAL-ROLLOUT.md) and [the bounded city queue](CITY-ROLLOUT-QUEUE.md). This is a rotating refresh target, not a promise that all cities refresh weekly or that all 50 will fit.

The broad `chicagoland` entry may advance to newer generated tiles. The original `19785f3c1ca31233` directory and exact `chicago-metro` `8d555e92cfa68b53` mirror remain byte-for-byte frozen. Every earlier published version, region, and public OSM source archive is retained until the 250 MB cumulative site ceiling stops further growth. No pruning occurs.

The monthly admission guard uses public GitHub Actions job history, counts failed and repeated attempts, rounds every job up, and reserves the full 22-minute job-timeout envelope before admitting work against a 100-minute threshold. It fails closed if accounting is unavailable. A strict total Actions-minute cap is impossible inside Actions: repeated rejected/manual gate runs still consume runner time. This guard prevents further costly admitted rollout work when it cannot fit; it is not an account-wide billing limit.

Only standard `ubuntu-24.04` runners are used. Build jobs stop at 15 minutes; the orchestrator has a 9-minute process watchdog and each region process group stops after at most 4 minutes. Rollout downloads have no retries, a 1.5 GB per-file limit and a conservative 3 GB cumulative run allowance. The full published site, including retained sources and recovery shards, must fit 250,000,000 bytes; each file is at most 24,000,000 bytes. Existing unexpired repository artifacts plus a conservative candidate artifact estimate must also fit 250 MB. The only uploaded artifact is the Pages artifact, retained for one day; no caches or duplicate diagnostic artifacts are used.

Durable recovery comes from `snapshot.json` plus hash-pinned transport shards published with the site, independently of expiring Actions artifacts. Corrupt or unavailable recovery data, stale live-manifest races, invalid regions, and over-budget candidates never replace current coverage. The initial checked-in snapshot is used only when the live descriptor is absent (HTTP 404) and the complete live manifest matches that known snapshot.

Run `python -m pip install -r requirements-dev.txt`, then `python -m unittest discover -s tests -v` and `python -m unittest discover -s publishing/tests -v`. A real generation additionally needs the official distribution's `osmium-tool`. `python tools/build_region.py` remains a legacy local-generation tool, not a deployment path. Output directories must be fresh.

Publication uses the existing repository's short-lived `GITHUB_TOKEN` and Pages OIDC permissions only. Accounting reads use the public API without credentials. No paid runner, new secret, private repository, custom domain or Cloudflare changes are introduced. GitHub Pages publication is public; the production Ride app and its Cloudflare regional release are separate.

## Manifest contract

`manifest.json`: `schemaVersion: 1`, `updatedAt`, `attribution`, `license`, `regions` array. Each region has `id`, `name`, `bounds` (west/south/east/north), `minzoom`, `maxzoom`, `sourceLayer`, `tiles` (URL-template array), `version`, `generatedAt`, `sourceUrl` (provenance), `sourceTimestamp`, `categories`, `tileCount`, `tileBytes`, `sha256Manifest`, and `sourceDownload`. Tile paths include a version identifier. Missing/invalid manifest regions must not be treated as coverage.
