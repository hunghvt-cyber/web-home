"""Read-only inventory for one cloud scope; output stays local and private."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cloud', required=True, choices=['gdrive', 'koofr'])
    parser.add_argument('--remote', required=True, help='Configured rclone remote and folder; e.g. gdrive:Photos')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if ':' not in args.remote or args.remote.startswith('-'):
        parser.error('Expected a configured rclone remote:folder')
    # Never overwrite an earlier audit; do not put inventory in Git/public output.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=args.output.parent, delete=False) as handle:
            temporary = Path(handle.name)
            subprocess.run(['rclone', 'lsjson', args.remote, '--recursive', '--files-only', '--hash'],
                           stdout=handle, check=True, timeout=7200)
        with temporary.open() as handle:
            if not isinstance(json.load(handle), list):
                raise ValueError('Inventory is not a list')
        os.link(temporary, args.output)  # Atomic publication; fails if destination exists.
        print(f'Inventory complete: {args.cloud}. No files moved or deleted.')
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
