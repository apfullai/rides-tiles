# Ride public cycling tiles

A bounded GitHub Pages pilot serving public OpenStreetMap cycling-infrastructure tiles for a personal, noncommercial map. This repository contains only standalone tile-generation code, configuration, documentation and public map data. It does not contain Ride application source or anyone's private routes.

The pilot includes an exact Chicagoland mirror (bounds -89, 41.05, -86.65, 43.25; content version `19785f3c1ca31233`) plus a compact New York City rectangle: west -74.05, south 40.65, east -73.85, north 40.90, at zooms 8–14. Coverage is not nationwide. Only the published `manifest.json` declares usable coverage, and a failed build must not replace the previous successful deployment.

## Data and attribution

© [OpenStreetMap contributors](https://www.openstreetmap.org/copyright). Public OSM data and derived databases are licensed under the [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/). Each published region includes provenance, source SHA-256 hashes, replication timestamps, tile hashes and a generation report. New regions include the filtered public OSM source extract; the Chicagoland mirror includes its entire public tile database archive and upstream-source provenance. Preserve attribution when displaying the map. This data is indicative infrastructure tagging, not a guarantee of legal access, safety, or current conditions.

Standalone code is MIT-licensed; this does not relicense the OSM data.

## Pipeline

A first-party GitHub Actions workflow downloads the public New York state Geofabrik extract, filters cycling ways, clips to the explicit configured bounds and generates raw (not HTTP-gzipped) MVT files. It also reconstructs the checked-in, public-only Chicagoland archive chunks and verifies every raw tile against the expected regional content version. No private repository is fetched. The vector source layer is `cycleinfra`; `kind` is one of `trail`, `protected`, `lane`, `shared_path`, `track`, `shared_lane`.

Run `python -m pip install -r requirements-dev.txt`, install `osmium-tool` from the operating system distribution, then `python -m unittest discover -s tests -v` and `python tools/build_region.py`. Output directories must be fresh. Build output is separate from source.

The pilot is capped at 25 build-job minutes, 18 generation-step minutes, 1.5 GB per input download, 100,000 nonempty tiles per region, and 750 MB published total. Source download timeout is 10 minutes per attempt with at most two retries. GitHub Pages itself has a 1 GB published-site maximum and 100 GB monthly soft bandwidth limit. No paid runner, third-party credential, custom domain, private repository dependency, or active recurring schedule is configured.

Publishing requires this public repository's Settings → Pages → Build and deployment source to be GitHub Actions. The workflow uses the repository's short-lived `GITHUB_TOKEN` and Pages OIDC only. GitHub Pages publication is public. The production Ride app is managed separately and must not be pointed at this pilot before deployed coverage, CORS, actual tile decoding, provenance, and browser fallback behavior are validated.

## Manifest contract

`manifest.json`: `schemaVersion: 1`, `updatedAt`, `attribution`, `license`, `regions` array. Each region has `id`, `name`, `bounds` (west/south/east/north), `minzoom`, `maxzoom`, `sourceLayer`, `tiles` (URL-template array), `version`, `generatedAt`, `sourceUrl` (provenance), `sourceTimestamp`, `categories`, `tileCount`, `tileBytes`, `sha256Manifest`, and `sourceDownload`. Tile paths include a version identifier. Missing/invalid manifest regions must not be treated as coverage.
