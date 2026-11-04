"""Remove legacy editors from the built site; never forward old share tokens."""
from pathlib import Path

NOTES_URL = 'https://hunghvt-notes.vercel.app/'

def retire(out):
    out = Path(out)
    for name in ('notes.js', 'shared-note.js', 'workspace.js', 'checklist.js'):
        (out / name).unlink(missing_ok=True)
    for route in ('notes', 'share', 'workspace'):
        message = 'Mở Notes' if route == 'notes' else 'Liên kết chia sẻ cũ đã ngừng hoạt động. Mở Notes để tạo liên kết mới.'
        redirect = ''
        if route == 'notes':
            (out / route).mkdir(parents=True, exist_ok=True)
            (out / route / 'index.html').unlink(missing_ok=True)
            continue
        (out / route).mkdir(parents=True, exist_ok=True)
        (out / route / 'index.html').write_text('<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer"><meta name="robots" content="noindex"><title>Notes</title><p>'+message+'</p><p><a href="'+NOTES_URL+'" rel="noreferrer">Mở Notes</a></p>'+redirect, encoding='utf-8')
