# Chicago metro publication

The full `pilot-pages.yml` build is the durable rebuild path: it restores broader Chicagoland from the checked-in public bootstrap, generates NYC, and invokes `publishing/append_metro.py` before any upload. The metro subset uses unchanged parent tiles and asserts version `8d555e92cfa68b53`, 3868 tiles, and bounds [-88.65,41.35,-86.8,42.65]. No expiring artifact is needed to recreate the metro source.

`append-metro.yml` is a one-off no-regeneration migration. It restores public artifact 11764694534 from run38290673759, which expires October14,2026. Do not use it after expiration. Its script verifies old tile hashes, preserves all old files, appends the metro first in the manifest, and creates a deterministic sanitized metro source archive.

For future complete rebuilds, manually dispatch `pilot-pages.yml` or change its existing source/config paths. Workflow-only changes do not automatically start this expensive build. Changes to parent tile geometry require updating the expected mirror version in coordination with the Cloudflare application. Keep old matching immutable versions until the application switch is verified.

Frozen-release guard: the script pins both original parent region versions. The current NYC generator uses timestamp-derived versions, so a fresh full rebuild intentionally fails validation until the refresh implementation replaces this guard with reviewed atomic all-region manifest, exact-mirror, and retained-version validation. Do not simply remove the guard. The metro archive can be reconstructed independently from the checked-in broad bootstrap and publishing metadata.
