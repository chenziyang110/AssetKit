# Project profiles and reusable units

AssetKit indexes resources **where their owning tool expects them**. Profile recognition reads bounded manifest markers; it never boots the engine or imports project code. `detect` finds up to three directory levels by default, with a 2000-directory bound. For a deep monorepo use a narrower project root or explicit `--profile` during capture.

| Profile | Evidence | Preserve | Supported hint/bundling |
|---|---|---|---|
| Unity | `ProjectSettings/ProjectVersion.txt` | `Assets/`, paired `.meta`, GUIDs | Pair present `.meta`; read GUID; identify scene/prefab/material/animation by extension |
| Unreal | `*.uproject` | `Content/` package paths | `/Game/...` package hint; do not guess a `.uasset` class or dependency closure |
| Godot | `project.godot` | Project-relative files, `.import`, `.uid` | `res://...`; pair existing sidecars; exclude `.godot/` cache |
| Web | Framework entries in `package.json` | `public/`, existing source assets | Scope-relative public URL hint; URL-encode filenames; do not guess arbitrary bundler imports |
| Android | Gradle project markers | `src/.../res/` resource qualifiers | `@drawable/name`, `@raw/name`, etc. where determinable; no resource ID for entries within values XML |
| iOS | `*.xcodeproj` | `.xcassets` asset-set structure | Group `.imageset`, `.appiconset`, `.colorset`; keep `Contents.json` as entry |
| Flutter | `sdk: flutter` in bounded `pubspec.yaml` | Existing asset paths | Path inventory only; verify pubspec registration and runtime loading separately |
| React Native | `react-native` or `expo` dependency | Asset names and density variants | Path inventory; do not claim Metro import or platform resource validation |
| Electron | `electron` dependency | Application resource paths | File references only; verify packaging separately |
| Tauri | `src-tauri/tauri.conf.json` | Icons/resource paths | File references only; verify bundle configuration separately |
| ML | `dvc.yaml`, or explicit `--profile ml` | Weights, indexes, datasets, configs | Streamed bytes only; no model deserialization, hardware or framework compatibility claims |
| Generic | No known marker | All existing project paths | Explicit paths/types; configurable extension discovery for proprietary formats |

A type is a broad family; `native_kind` supplies a narrower hint. For example, Unreal `.uasset` remains a package, not a falsely inferred mesh, material, animation or blueprint. Native hints are advisory, and engine import/build validation remains authoritative.

## Reusable unit, not one record per incidental file

A plain image is one unit. A Unity prefab plus its `.meta` is one unit (not its complete graph). A glTF file plus its explicitly declared local buffers/images is one unit. An iOS image set is one unit. For a model package with a few weight shards, select the versioned directory with `--bundle --entry config.json` or its index.

Explicit directory bundles are limited to 128 files and 4096 directory entries, with a 64 KiB card bound. These limits avoid unbounded records; a large dataset should use a versioned manifest/index, not thousands of paths in model context. The manifest's hash verifies only the manifest; it does not verify all referenced payloads. Remote glTF URIs are rejected, not downloaded. A `.glb` or engine package may still have undeclared dependencies.

```bash
assetctl capture Assets/Characters/Hero.prefab --use "可操作玩家角色"
assetctl capture Content/UI/WBP_Menu.uasset --use "游戏主菜单界面"
assetctl capture App/Assets.xcassets/Logo.imageset --use "品牌 Logo"
assetctl capture models/robot --bundle --entry config.json --use "机器人识别模型的本地部署包"
```

Here `assetctl` denotes `python <SKILL_DIR>/scripts/assetctl.py --root <PROJECT_ROOT>`.

## Project-specific discovery policy

Merge a `discovery` section into the existing `.assets/config.json`; do not replace `project_id` or the rest of the file:

```json
{
  "discovery": {
    "roots": ["apps/web/public", "games/client/Assets", "docs"],
    "extensions": {".qrc": "template", ".bank": "audio"},
    "exclude_globs": ["*/ThirdParty/*", "docs/generated/*"]
  }
}
```

`roots` narrows scan/gate discovery; explicit capture still allows a reviewed exact path elsewhere. Extension values must be one of the standard type families. Exclusion patterns use Python `fnmatch` against POSIX relative paths; they are not a complete gitignore language. Git inventories additionally respect Git's untracked-file ignore rules. Secret/tool/cache exclusions cannot be overridden by this policy. Unknown proprietary extensions can always be explicitly captured with `--type other`.

## Evidence used for the adapters

- Unity metadata: https://docs.unity3d.com/6000.0/Documentation/Manual/AssetMetadata.html
- Unreal redirectors: https://dev.epicgames.com/documentation/en-us/unreal-engine/asset-redirectors-in-unreal-engine
- Godot import process: https://docs.godotengine.org/en/stable/tutorials/assets_pipeline/import_process.html
- Android resource organization: https://developer.android.com/guide/topics/resources/providing-resources
- Next.js public directory: https://nextjs.org/docs/app/api-reference/file-conventions/public-folder

These references explain conventions. Synthetic adapter tests do not substitute for opening and building a real project in each engine/version.
