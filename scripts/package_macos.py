"""Build an Apple Silicon application and a per-user native Installer package."""
import hashlib
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
import xml.etree.ElementTree as ET

from scripts.package_windows import ROOT, REVISION, RELEASE, download, stage_notices, smoke_package, write_build_info

WORK = ROOT / 'local/mac-package'
APP = ROOT / 'dist/Cedexia Nexus.app'
ARCHIVE = 'llama-b12347-bin-macos-arm64.tar.gz'
SHA256 = 'ec208b4889a87b68a5193f3f303d14ba19f1101efea9d3343ba331d79cd3cfbf'
RUNTIME_FILE = re.compile(r'llama-completion|lib(?:llama(?:-common|-completion-impl)?|mtmd|ggml(?:-base|-cpu|-blas|-metal|-rpc)?)(?:\.\d+)*\.dylib')


def stage_runtime():
    runtime = WORK / 'runtime'
    if runtime.exists():
        shutil.rmtree(runtime)
    runtime.mkdir()
    archive = download(RELEASE + ARCHIVE, WORK / ARCHIVE, SHA256)
    with tarfile.open(archive) as bundle:
        for entry in bundle.getmembers():
            name = Path(entry.name).name
            if not RUNTIME_FILE.fullmatch(name):
                continue
            target = runtime / name
            if entry.issym():
                if Path(entry.linkname).name != entry.linkname or not RUNTIME_FILE.fullmatch(entry.linkname):
                    raise ValueError('Unsafe runtime symlink')
                target.symlink_to(entry.linkname)
            elif entry.isfile():
                with bundle.extractfile(entry) as source, target.open('xb') as output:
                    shutil.copyfileobj(source, output)
                target.chmod(0o755)
            else:
                raise ValueError('Unexpected runtime archive member')
    version = subprocess.run([str(runtime / 'llama-completion'), '--version'], capture_output=True, text=True, check=True, timeout=30)
    match = re.search(r'\bcommit ([0-9a-f]{8,40})\)', version.stdout + version.stderr)
    if not match or not REVISION.startswith(match[1]):
        raise ValueError('Unexpected runtime revision')
    subprocess.run([str(runtime / 'llama-completion'), '--offline', '--list-devices'], check=True, timeout=30)
    return runtime


def distribution_xml(version):
    root = ET.Element('installer-gui-script', {'minSpecVersion': '2'})
    ET.SubElement(root, 'title').text = 'Cedexia Nexus'
    ET.SubElement(root, 'options', {'customize': 'never', 'require-scripts': 'false', 'hostArchitectures': 'arm64'})
    ET.SubElement(root, 'domains', {'enable_anywhere': 'false', 'enable_currentUserHome': 'true', 'enable_localSystem': 'false'})
    volume = ET.SubElement(root, 'volume-check')
    versions = ET.SubElement(volume, 'allowed-os-versions')
    ET.SubElement(versions, 'os-version', {'min': '14.0'})
    for tag, filename in [('welcome', 'welcome.html'), ('readme', 'readme.html'), ('conclusion', 'finished.html')]:
        ET.SubElement(root, tag, {'file': filename, 'mime-type': 'text/html'})
    outline = ET.SubElement(root, 'choices-outline')
    ET.SubElement(outline, 'line', {'choice': 'app'})
    choice = ET.SubElement(root, 'choice', {'id': 'app', 'visible': 'false', 'title': 'Cedexia Nexus'})
    ET.SubElement(choice, 'pkg-ref', {'id': 'com.cedexia.nexus'})
    ref = ET.SubElement(root, 'pkg-ref', {'id': 'com.cedexia.nexus', 'version': version, 'onConclusion': 'None'})
    ref.text = 'CedexiaNexus-component.pkg'
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def main():
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise SystemExit('Build on an Apple Silicon Mac.')
    import json
    if json.loads((ROOT / 'config/model-manifest.json').read_text())['runtime']['candidate_revision'] != REVISION:
        raise SystemExit('Runtime pin must match the model manifest.')
    version = (ROOT / 'installers/version.txt').read_text().strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Invalid package version')
    WORK.mkdir(parents=True, exist_ok=True)
    build_info = write_build_info(WORK)
    runtime = stage_runtime()
    subprocess.run([
        sys.executable, '-m', 'PyInstaller', '--windowed', '--onedir', '--noconfirm', '--noupx',
        '--name', 'Cedexia Nexus', '--osx-bundle-identifier', 'com.cedexia.nexus', '--target-arch', 'arm64',
        '--paths', str(ROOT), '--distpath', str(ROOT / 'dist'), '--workpath', str(WORK / 'build'),
        '--specpath', str(WORK), '--add-data', f'{ROOT / "nexus_ui/assets/icons"}:nexus_ui/assets/icons',
        '--add-data', f'{ROOT / "config/model-manifest.json"}:config',
        '--add-data', f'{build_info}:config',
        '--add-binary', f'{runtime}/*:runtime', str(ROOT / 'scripts/windows_desktop_entry.py'),
    ], cwd=ROOT, check=True)
    resources = APP / 'Contents/Resources'
    stage_notices(resources)
    with (APP / 'Contents/Info.plist').open('rb') as stream:
        info = plistlib.load(stream)
    info.update(CFBundleShortVersionString=version, CFBundleVersion=version, LSMinimumSystemVersion='14.0')
    explanation = 'Cedexia Nexus zeigt den Namen des verbundenen WLANs an, damit du den passenden Adapter beim Koppeln erkennst.'
    info.update(NSLocationUsageDescription=explanation, NSLocationWhenInUseUsageDescription=explanation)
    info['NSLocalNetworkUsageDescription'] = 'Cedexia Nexus findet andere Geräte im lokalen Netz und verbindet sie nach deiner Bestätigung.'
    with (APP / 'Contents/Info.plist').open('wb') as stream:
        plistlib.dump(info, stream)
    (resources / 'licenses/Metal-runtime.txt').write_text(f'{RELEASE}{ARCHIVE}\nSHA-256: {SHA256}\nRevision: {REVISION}\n', encoding='utf-8')
    subprocess.run(['codesign', '--force', '--deep', '--sign', '-', str(APP)], check=True)
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(APP)], check=True)
    smoke_package(APP / 'Contents/MacOS/Cedexia Nexus', WORK)
    payload = WORK / 'payload'
    if payload.exists():
        shutil.rmtree(payload)
    shutil.copytree(APP, payload / 'Applications/Cedexia Nexus.app', symlinks=True)
    components = WORK / 'components.plist'
    subprocess.run(['pkgbuild', '--analyze', '--root', str(payload), str(components)], check=True)
    with components.open('rb') as stream:
        entries = plistlib.load(stream)
    for entry in entries:
        entry['BundleIsRelocatable'] = False
        entry['BundleHasStrictIdentifier'] = True
    with components.open('wb') as stream:
        plistlib.dump(entries, stream)
    subprocess.run(['pkgbuild', '--root', str(payload), '--component-plist', str(components), '--install-location', '/',
                    '--identifier', 'com.cedexia.nexus', '--version', version, str(WORK / 'CedexiaNexus-component.pkg')], check=True)
    definition = WORK / 'Distribution.xml'
    definition.write_bytes(distribution_xml(version))
    output = ROOT / 'dist/installers'
    output.mkdir(exist_ok=True)
    package = output / 'CedexiaNexus-macOS-arm64.pkg'
    subprocess.run(['productbuild', '--distribution', str(definition), '--resources', str(ROOT / 'installers/macos'),
                    '--package-path', str(WORK), str(package)], check=True)
    with package.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    package.with_suffix('.pkg.sha256').write_text(f'{digest}  {package.name}\n')
    print(f'Installer ready: {package.name}', flush=True)


if __name__ == '__main__':
    main()
