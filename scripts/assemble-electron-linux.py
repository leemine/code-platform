"""Assemble a portable Linux bundle and a per-system Debian test installer."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tarfile
from pathlib import Path

from build_config import load_build_config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', choices=('native', 'external'), required=True)
    parser.add_argument('--dist-dir', type=Path, help='Separate backend/output directory; retain running bundles')
    args = parser.parse_args()
    if platform.system() != 'Linux':
        parser.error('Linux packaging requires a Linux build host')
    root = Path(__file__).resolve().parents[1]
    dist = args.dist_dir.resolve() if args.dist_dir else root / 'dist'
    config = load_build_config(root)
    arch = {'x86_64': 'amd64', 'aarch64': 'arm64'}.get(platform.machine())
    if arch is None:
        parser.error('Unsupported Linux architecture')
    desktop = root / 'jiuwenswarm/channels/desktop/electron'
    source = desktop / 'node_modules/electron/dist'
    backend = dist / config.dist_dir_name
    if not (source / 'electron').is_file() or not (backend / config.executable_name).is_file():
        parser.error('Build Electron dependencies and the frozen backend first')
    name = f'workswarm-{args.profile}'
    bundle = dist / f'{name}-linux-{arch}'
    if bundle.exists():
        parser.error(f'Output already exists: {bundle}; retain or move the previous artifact first')
    shutil.copytree(source, bundle)
    # Electron identifies the unrenamed development executable as unpackaged.
    # Rename our copied runtime, preserving the official binary bytes.
    (bundle / "electron").rename(bundle / "workswarm-desktop")
    app = bundle / 'resources/app'
    app.mkdir(parents=True)
    for path in desktop.iterdir():
        if path.suffix in {'.cjs', '.json', '.ico', '.icns', '.svg'} and path.name != 'package-lock.json':
            shutil.copy2(path, app / path.name)
    shutil.copytree(backend, bundle / 'resources/backend')
    # Existing Electron browser bridge runs its pinned bundled MCP via Node mode.
    mcp_zip = root / 'jiuwenswarm/resources/runtime/playwright-mcp/playwright-mcp-0.0.78.zip'
    import zipfile
    with zipfile.ZipFile(mcp_zip) as archive:
        archive.extractall(app)
    launcher = bundle / name
    launcher.write_text('#!/bin/sh\nexec "$(dirname "$(readlink -f "$0")")/workswarm-desktop" "$@"\n')
    launcher.chmod(0o755)
    (bundle / 'BUILD.json').write_text(json.dumps({
        'profile': args.profile, 'version': config.version, 'architecture': arch,
        'core_included': args.profile == 'native',
        'provider_cli_bundled': False,
    }, indent=2) + '\n')
    archive = bundle.with_suffix('.tar.gz')
    with tarfile.open(archive, 'w:gz', compresslevel=3) as output:
        output.add(bundle, arcname=bundle.name)
    stage = (dist / '.staging' if args.dist_dir else root / 'build') / f'deb-{name}-{arch}'
    stage.mkdir(parents=True, exist_ok=False)
    target = stage / 'opt' / name
    shutil.copytree(bundle, target)
    control = stage / 'DEBIAN'
    control.mkdir()
    (control / 'control').write_text(
        f'Package: {name}\nVersion: {config.version.replace(".beta", "~beta")}\nArchitecture: {arch}\n'
        'Maintainer: WorkSwarm contributors\nSection: utils\nPriority: optional\n'
        'Depends: libgtk-3-0, libnss3, libasound2, libgbm1, libxss1\n'
        f'Description: WorkSwarm {args.profile} desktop test build\n')
    applications = stage / 'usr/share/applications'
    applications.mkdir(parents=True)
    (applications / f'{name}.desktop').write_text(
        '[Desktop Entry]\nType=Application\nName=WorkSwarm '+args.profile+'\n'
        f'Exec=/opt/{name}/{name}\nTerminal=false\nCategories=Development;\n')
    # Chromium's supported setuid sandbox is retained in the installed package.
    (target / 'chrome-sandbox').chmod(0o4755)
    deb = dist / f'{name}_{config.version}_{arch}.deb'
    subprocess.run(['dpkg-deb', '-Zgzip', '-z3', '--root-owner-group', '--build', str(stage), str(deb)], check=True)
    for path in (archive, deb):
        digest = hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()
        path.with_suffix(path.suffix + '.sha256').write_text(f'{digest}  {path.name}\n')
        print(path)


if __name__ == '__main__':
    main()
