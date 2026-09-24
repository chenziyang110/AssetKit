"""Bounded, read-only project and asset classification. Never import project code."""
from __future__ import annotations
import json
import fnmatch
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import quote

PROFILES = ('generic', 'web', 'unity', 'unreal', 'godot', 'android', 'ios', 'flutter', 'react-native', 'electron', 'tauri', 'ml')
SKIP = {'.git', '.assets', '.agents', '.claude', '.work', '__pycache__', 'node_modules', '.next', '.nuxt', '.venv', 'venv', '.godot', '.dart_tool', '.gradle', 'Pods', 'DerivedData', 'Library', 'Temp', 'Obj', 'Logs', 'Binaries', 'Intermediate', 'Saved', 'DerivedDataCache', 'target', 'dist', 'build', 'coverage'}
SECRET_EXT = {'.pem', '.key', '.p12', '.pfx', '.jks', '.keystore', '.mobileprovision'}
TYPES = {
 'document': '.md .mdx .txt .pdf .docx .pptx .xlsx .rst',
 'image': '.png .jpg .jpeg .webp .gif .svg .avif .ico .bmp .tga .exr .hdr .ktx .ktx2 .dds .aseprite',
 'audio': '.wav .mp3 .ogg .flac .m4a .aac .aiff .bank',
 'video': '.mp4 .webm .mov .mkv',
 'model-3d': '.glb .gltf .fbx .obj .blend .usd .usdz .usda .stl',
 'model-ml': '.onnx .safetensors .gguf .pt .pth .tflite .mlmodel .mlpackage',
 'dataset': '.csv .tsv .parquet .arrow .jsonl',
 'design': '.fig .psd .ai .sketch .xd',
 'template': '.prefab .unity .tscn .tres .scn .res .uasset .umap .mat .material .anim .controller .shader .shadergraph .compute .ttf .otf .woff .woff2 .po .pot .strings .stringsdict .lottie .atlas .spritesheet',
}
EXTENSIONS = {ext: kind for kind, words in TYPES.items() for ext in words.split()}
BUNDLES = {'.imageset', '.appiconset', '.colorset', '.brandassets', '.mlpackage'}
NATIVE = {'.prefab':'prefab', '.unity':'scene', '.tscn':'scene', '.umap':'scene', '.uasset':'unreal-package', '.tres':'resource', '.mat':'material', '.anim':'animation', '.controller':'animation-controller', '.ttf':'font', '.woff':'font', '.woff2':'font', '.otf':'font', '.po':'localization', '.strings':'localization', '.shader':'shader', '.shadergraph':'shader'}


def allowed(path: str) -> bool:
    p = Path(path)
    return (not any(part in SKIP for part in p.parts) and not any(ord(c) < 32 for c in path)
            and p.suffix.lower() not in SECRET_EXT
            and not any(part.lower().startswith('.env') for part in p.parts)
            and p.name.lower() not in {'credentials.json', 'credentials', 'id_rsa', 'id_ed25519', 'service-account.json', 'google-services.json', 'googleservice-info.plist'})


def head(path: Path, limit: int = 65536) -> bytes:
    if path.is_symlink() or not path.is_file():
        return b''
    with path.open('rb') as f:
        return f.read(limit)


def at(directory: Path) -> list[tuple[str, str]]:
    """Detect at one scope. Manifest markers are evidence, not engine compatibility."""
    results = []
    markers = [('unity','ProjectSettings/ProjectVersion.txt'), ('godot','project.godot'),
               ('tauri','src-tauri/tauri.conf.json'), ('android','build.gradle'), ('android','build.gradle.kts'),
               ('ml','dvc.yaml')]
    for profile, marker in markers:
        if (directory / marker).is_file():
            results.append((profile, marker))
    try:
        names = list(directory.iterdir())
    except OSError:
        return results
    for p in names:
        if p.suffix == '.uproject' and p.is_file(): results.append(('unreal', p.name))
        if p.suffix == '.xcodeproj' and p.is_dir(): results.append(('ios', p.name))
    if re.search(rb'sdk:\s*flutter\b', head(directory / 'pubspec.yaml')):
        results.append(('flutter', 'pubspec.yaml'))
    try:
        package = json.loads(head(directory / 'package.json') or b'{}')
        deps = {**package.get('dependencies', {}), **package.get('devDependencies', {})}
        for profile, keys in [('electron', {'electron'}), ('react-native', {'react-native','expo'}),
                              ('web', {'next','react','vue','svelte','vite','astro','@angular/core'})]:
            if keys & deps.keys(): results.append((profile, 'package.json'))
    except (ValueError, TypeError, AttributeError):
        pass
    return list(dict.fromkeys(results))


def detect(root: Path, depth: int = 3) -> list[dict]:
    found, visited = [], 0
    for directory, dirs, _ in os.walk(root, followlinks=False):
        visited += 1
        if visited > 2000:
            raise ValueError('DETECTION_LIMIT: select a smaller --root (more than 2000 directories)')
        p = Path(directory)
        rel = p.relative_to(root)
        dirs[:] = sorted(d for d in dirs if d not in SKIP and not (p/d).is_symlink()) if len(rel.parts) < depth else []
        for profile, evidence in at(p):
            found.append({'profile':profile, 'scope':rel.as_posix(), 'evidence':(rel/evidence).as_posix()})
    return found or [{'profile':'generic','scope':'.','evidence':'no recognized marker within detection bounds'}]


def context(root: Path, path: str, override: str | None = None) -> dict:
    p = root / path
    directory = p if p.is_dir() else p.parent
    while True:
        found = at(directory)
        if found:
            return {'profile':override or found[0][0], 'scope':directory.relative_to(root).as_posix(), 'evidence':found[0][1]}
        if directory == root: break
        directory = directory.parent
    return {'profile':override or 'generic','scope':'.','evidence':'explicit override' if override else 'no ancestor marker'}


def kind(path: str, extensions: dict | None = None) -> str | None:
    p = Path(path)
    if p.suffix.lower() in {'.imageset','.appiconset','.brandassets'}: return 'image'
    if p.suffix.lower()=='.colorset': return 'design'
    if p.name.endswith(('.safetensors.index.json','.bin.index.json')): return 'model-ml'
    if p.suffix.lower() in {'.meta', '.import', '.uid'}: return None
    if p.name in {'Contents.json', 'package.json', 'package-lock.json', 'tsconfig.json', 'project.godot'}: return None
    if extensions and p.suffix.lower() in extensions: return extensions[p.suffix.lower()]
    if p.suffix.lower() in EXTENSIONS: return EXTENSIONS[p.suffix.lower()]
    if p.suffix.lower() == '.json' and ('locales' in p.parts or 'i18n' in p.parts): return 'template'
    if p.suffix.lower() == '.xml' and 'res' in p.parts: return 'template'
    if p.suffix.lower() == '.asset' and 'Assets' in p.parts: return 'template'
    if p.suffix.lower() == '.dvc': return 'dataset'
    return None


def bundle_parent(path: str) -> str:
    p = Path(path)
    for parent in [p, *p.parents]:
        if parent.suffix.lower() in BUNDLES:
            return parent.as_posix()
    return path


def git(root: Path, arguments: list[str], limit: int = 16*1024*1024) -> bytes:
    # No shell, external diff, text conversion, or project hooks. Bound output on disk.
    import tempfile
    with tempfile.TemporaryFile() as output:
        proc = subprocess.run(['git', '-c', 'core.fsmonitor=false', '-c', 'core.untrackedCache=false', '-C', str(root), *arguments], stdout=output, stderr=subprocess.PIPE, timeout=30,
                              env={**os.environ, 'GIT_OPTIONAL_LOCKS':'0', 'GIT_TERMINAL_PROMPT':'0'})
        if proc.returncode: raise ValueError('GIT_ERROR: ' + proc.stderr.decode('utf-8','replace')[:400])
        if output.tell() > limit: raise ValueError('INVENTORY_LIMIT: Git output exceeds 16 MiB; select a smaller project scope')
        output.seek(0)
        return output.read()


def candidates(root: Path, since: str | None = None, policy: dict | None = None) -> tuple[list[str], str]:
    policy = policy or {}
    try:
        is_git = git(root, ['rev-parse', '--is-inside-work-tree']).strip() == b'true'
    except (ValueError, OSError):
        is_git = False
    if since and not is_git: raise ValueError('GIT_REQUIRED: --since requires a Git working tree')
    if is_git:
        if since:
            ref = git(root, ['rev-parse','--verify','--end-of-options', since+'^{commit}']).decode().strip()
            raw = git(root, ['diff','--no-ext-diff','--no-textconv','--name-only','--relative','--diff-filter=ACMRT','-z',ref,'--','.'])
            raw += git(root, ['ls-files','--others','--exclude-standard','-z','--','.'])
        else:
            raw = git(root, ['ls-files','--cached','--others','--exclude-standard','-z','--','.'])
        paths = [v.decode('utf-8', 'strict') for v in raw.split(b'\0') if v]
        mode = 'git-changes' if since else 'git-inventory'
    else:
        paths, mode = [], 'filesystem-inventory'
        visited = 0
        for directory, dirs, files in os.walk(root, followlinks=False):
            visited += len(dirs) + len(files)
            if visited > 100000: raise ValueError('INVENTORY_LIMIT: more than 100000 entries; narrow --root')
            d = Path(directory)
            dirs[:] = sorted(n for n in dirs if n not in SKIP and not (d/n).is_symlink())
            paths.extend((d/n).relative_to(root).as_posix() for n in files)
    result = set()
    for path in paths:
        if not allowed(path) or not (root/path).is_file(): continue
        if any(fnmatch.fnmatchcase(path, pattern) for pattern in policy.get('exclude_globs', [])): continue
        if not any(prefix=='.' or path.startswith(prefix.rstrip('/')+'/') for prefix in policy.get('roots',['.'])): continue
        grouped = bundle_parent(path)
        if kind(path,policy.get('extensions')) or grouped != path:
            result.add(grouped)
    return sorted(result), mode


def hints(root: Path, primary: str, override: str | None = None) -> dict:
    ctx = context(root, primary, override)
    path, profile = Path(primary), ctx['profile']
    scope = root if ctx['scope'] == '.' else root / ctx['scope']
    relative = (root/path).relative_to(scope).as_posix()
    result = {**ctx, 'native_kind':NATIVE.get(path.suffix.lower(), kind(primary) or 'bundle'),
              'dependency_scope':'declared files and known sidecars only; not a complete engine dependency graph'}
    if profile == 'unity':
        match = re.search(rb'^guid:\s*([0-9a-f]{32})\s*$', head(root/(primary+'.meta'),4096), re.M)
        if match: result['native_ref'] = {'guid':match.group(1).decode(), 'path':relative}
        elif relative.startswith('Assets/'): result['import_required'] = 'Unity .meta/GUID is missing; import in the editor without inventing a GUID'
    elif profile == 'unreal' and relative.startswith('Content/'):
        result['native_ref'] = {'package':'/Game/'+str(Path(relative[8:]).with_suffix('')).replace('\\','/')}
    elif profile == 'godot': result['native_ref'] = 'res://'+relative
    elif '/res/' in '/'+relative:
        match = re.search(r'(?:^|/)res/([^/]+)/([^/]+)$', relative)
        if match:
            resource_type = match[1].split('-')[0]
            if resource_type in {'drawable','mipmap','raw','font','layout','anim','menu','xml'}:
                result['native_ref'] = '@'+resource_type+'/'+Path(match[2]).stem.removesuffix('.9')
    elif profile == 'web' and relative.startswith('public/'):
        result['native_ref'] = '/'+quote(relative[7:])
    if path.name == 'Contents.json' and path.parent.suffix in BUNDLES:
        result['native_ref'] = {'asset_catalog_name':path.parent.stem}
    data = head(root/primary,4096)
    if data.startswith(b'\x89PNG\r\n\x1a\n') and len(data)>=24:
        import struct
        width,height = struct.unpack('>II', data[16:24])
        result['dimensions'] = {'width':width, 'height':height, 'basis':'PNG header, not a full decoder validation'}
    if data.startswith(b'version https://git-lfs.github.com/spec/v1'):
        result['unmaterialized'] = 'git-lfs-pointer'
    if path.suffix == '.dvc': result['unmaterialized'] = 'dvc-pointer'
    return result
