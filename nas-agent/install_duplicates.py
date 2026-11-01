#!/usr/bin/env python3
"""Prepare a scan allowlist from existing native rclone remotes, without printing secrets."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--drive-remote')
    parser.add_argument('--koofr-remote')
    args = parser.parse_args()
    if os.getuid() == 0: raise SystemExit('Run as the NAS admin account, not root.')
    if not os.path.ismount('/vol1'): raise SystemExit('/vol1 is not mounted.')
    rclone = shutil.which('rclone')
    if not rclone: raise SystemExit('rclone is not installed for this user.')
    # The parsed credentials stay in process memory; neither payload nor provider errors are printed.
    try:
        result = subprocess.run([rclone, 'config', 'dump'], capture_output=True, text=True, check=True, timeout=20)
        config = json.loads(result.stdout)
    except Exception: raise SystemExit('Cannot read existing rclone configuration; credentials were not printed.')
    roots = {}
    for cloud, provider, selected in [('gdrive', 'drive', args.drive_remote), ('koofr', 'koofr', args.koofr_remote)]:
        names = [name for name, value in config.items() if value.get('type') == provider and re.fullmatch(r'[a-zA-Z0-9_-]+', name)]
        if selected:
            if selected not in names: raise SystemExit('Selected remote does not match provider: '+cloud)
            name = selected
        elif len(names) == 1: name = names[0]
        elif len(names) > 1: raise SystemExit('Multiple remotes for '+cloud+'; use --'+('drive' if cloud == 'gdrive' else 'koofr')+'-remote NAME.')
        else: continue
        roots[cloud] = {'remote': name, 'path': ''}
    if not roots: raise SystemExit('No existing native Drive/Koofr remotes found; cloud login is required first.')
    directory = Path.home() / '.config/homepage-duplicates'
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.is_symlink() or directory.stat().st_uid != os.getuid(): raise SystemExit('Unsafe config directory.')
    directory.chmod(0o700)
    path = directory / 'config.json'
    state = Path('/vol1') / ('homepage-duplicates-'+str(os.getuid()))
    if path.exists() or path.is_symlink():
        if path.is_symlink() or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077: raise SystemExit('Unsafe config file.')
        current = json.loads(path.read_text())
        if current.get('roots') != roots: raise SystemExit('Existing cloud allowlist differs; preserved without changes.')
        state = Path(current['state_dir'])
    else:
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as handle:
            json.dump({'state_dir': str(state), 'roots': roots, 'rclone_path': rclone}, handle)
    if not str(state).startswith('/vol1/') or state.is_symlink(): raise SystemExit('Unsafe state directory.')
    if not state.resolve().is_relative_to(Path('/vol1').resolve()): raise SystemExit('State resolves outside HDD.')
    state.mkdir(mode=0o700, parents=True, exist_ok=True); state.chmod(0o700)
    source = Path(__file__).resolve().parent
    install = Path('/vol1') / ('homepage-terminal-'+__import__('getpass').getuser())
    if install.is_symlink() or not install.is_dir() or install.stat().st_uid != os.getuid(): raise SystemExit('Unsafe agent install directory.')
    if not (install / 'agent.py').is_file(): raise SystemExit('Homepage terminal agent must be installed first.')
    if (install / 'agent.py').is_symlink(): raise SystemExit('Unsafe agent file.')
    # Preserve the previous agent for rollback. Do not touch its keys or tmux server.
    backup = install / 'agent.py.before-duplicates'
    if backup.is_symlink(): raise SystemExit('Unsafe backup path.')
    if not backup.exists(): shutil.copy2(install / 'agent.py', backup)
    if (install / 'duplicates.py').is_symlink(): raise SystemExit('Unsafe scanner file.')
    if (install / 'cloud_cleanup.py').is_symlink(): raise SystemExit('Unsafe cleanup file.')
    for name in ('agent.py','duplicates.py'):
        previous=install/(name+'.before-cleanup')
        if previous.is_symlink():raise SystemExit('Unsafe pre-cleanup backup path.')
        if (install/name).exists() and not previous.exists():shutil.copy2(install/name,previous)
    for name in ('agent.py', 'duplicates.py', 'cloud_cleanup.py'):
        shutil.copyfile(source / name, install / name); (install / name).chmod(0o600)
    # Installing this reviewed release explicitly enables recoverable cleanup; preserve all other settings.
    saved = json.loads(path.read_text()); saved['cleanup_enabled'] = True
    fd, temporary = tempfile.mkstemp(dir=directory, prefix='.cleanup-')
    try:
        with os.fdopen(fd, 'w') as handle:
            json.dump(saved, handle); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
    subprocess.run(['systemctl', '--user', 'restart', 'homepage-terminal.service'], check=True)
    subprocess.run(['systemctl', '--user', 'is-active', 'homepage-terminal.service'], check=True)
    print('DUPLICATES_INSTALL=PASS; clouds='+','.join(roots))
    print('SCANNER_VERSION=3; recoverable cleanup enabled; existing cloud configuration preserved.')
    print('METADATA_SIZE_FIX=enabled; unknown-size files are counted and excluded from cleanup.')
    print('No scan or cleanup started by installation. No cloud data changed. Keys preserved.')


if __name__ == '__main__': main()
