"""Build and exercise a Windows setup around the self-contained application."""
import hashlib
import os
from pathlib import Path
import platform
import subprocess
from tempfile import TemporaryDirectory

from scripts import package_windows


def main():
    if platform.system() != 'Windows':
        raise SystemExit('Build the Windows setup on Windows x64.')
    package_windows.main()
    compiler = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'Inno Setup 6/ISCC.exe'
    if not compiler.is_file():
        raise SystemExit('Inno Setup 6 is required on the build machine: https://jrsoftware.org/isinfo.php')
    version = (package_windows.ROOT / 'installers/version.txt').read_text().strip()
    subprocess.run([str(compiler), f'/DAppVersion={version}', str(package_windows.ROOT / 'installers/windows/setup.iss')], check=True)
    setup = package_windows.ROOT / 'dist/installers/CedexiaNexus-Windows-x64-Setup.exe'
    with setup.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    setup.with_suffix('.exe.sha256').write_text(f'{digest}  {setup.name}\n')
    # An isolated CI install and update, then launch from the installed location.
    with TemporaryDirectory(prefix='nexus-installer-') as directory:
        target = Path(directory) / 'Installiert mit Leerzeichen'
        for _ in range(2):
            subprocess.run([str(setup), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', f'/DIR={target}'], check=True, timeout=180)
            package_windows.smoke_package(target / 'CedexiaNexus.exe', package_windows.WORK)
        subprocess.run([str(target / 'unins000.exe'), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'], check=True, timeout=90)
        if (target / 'CedexiaNexus.exe').exists():
            raise ValueError('Uninstallation left the application executable behind.')
    print('Windows installer, update, installed app and uninstall checks passed.', flush=True)


if __name__ == '__main__':
    main()
