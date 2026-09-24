# Security policy

## Supported scope

The 1.x CLI is maintained for trusted local working copies. It is not a sandbox, access-control service or license authority. Local agents and users with filesystem write access can bypass instructions and alter files. Advisory locks coordinate cooperating processes only. Do not share a live SQLite catalog across machines or network filesystems.

Asset contents, metadata and search results are untrusted data, never instructions. Runtime tools do not execute project scripts, deserialize model weights, fetch remote glTF resources, upload assets, generate embeddings or call model APIs. Git inventory disables external diff/textconv and filesystem-monitor helpers. Obvious credential/signing files, tool directories and build caches are excluded; these filename rules are not comprehensive data-loss prevention or secret scanning.

Symlink/redirected metadata paths are rejected. Exact-path capture also rejects symlink asset paths. These checks reduce accidental redirection but do not establish race-proof isolation against hostile local processes. Media metadata is bounded header inspection, not a hardened full decoder. Native references are hints; validate a real import/build before shipping an engine asset.

## Reporting

Do not post secrets, proprietary assets or working exploit data in a public issue. Use the repository's private vulnerability reporting feature when it is enabled, or contact the repository owner through an available private channel before sending details. This repository does not claim that private reporting has already been enabled, nor does it promise a response-time SLA.

Include the AssetKit version/commit, OS/Python versions, a sanitized minimal reproduction and whether the issue affects authoritative records or only a derived cache. Preserve original data and use `reindex` for index-only corruption rather than deleting asset records.
