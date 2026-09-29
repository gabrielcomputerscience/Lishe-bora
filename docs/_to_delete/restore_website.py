"""One-off: copy the homepage banner, stats, section backgrounds and uploaded media records from the
pre-rebuild database backup into the demo and pilot databases."""
import sqlite3, sys
SRC = '../docs/_to_delete/lishebora_old_2026-09-24.db'
o = sqlite3.connect(SRC)
cols = [r[1] for r in o.execute('pragma table_info(cms_media)')]
media = o.execute(f"select {','.join(cols)} from cms_media").fetchall()
blocks = {k: o.execute('select data,published_data,status,version,published_at from cms_blocks where key=?', (k,)).fetchone()
          for k in ('hero', 'stats', 'backgrounds')}
for db in sys.argv[1:] or ['lishebora_pilot.db', 'lishebora.db']:
    n = sqlite3.connect(db, timeout=20)
    for m in media:
        n.execute(f"insert or ignore into cms_media ({','.join(cols)}) values ({','.join('?' * len(cols))})", m)
    for k, v in blocks.items():
        n.execute('update cms_blocks set data=?,published_data=?,status=?,version=?,published_at=? where key=?', (*v, k))
    n.commit()
    print(db, 'media:', n.execute('select count(*) from cms_media').fetchone()[0], 'website settings restored')
