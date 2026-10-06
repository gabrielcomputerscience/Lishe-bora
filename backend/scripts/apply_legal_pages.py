"""Replace the one-line placeholder Privacy notice / Terms of use pages in existing databases with the starter texts
in app/seed/legal.py. Pages that were already edited are left alone.   python scripts/apply_legal_pages.py lishebora.db ..."""
import sqlite3
import sys
from pathlib import Path

ns: dict = {}
exec((Path(__file__).resolve().parent.parent / "app" / "seed" / "legal.py").read_text(encoding="utf-8"), ns)
for db in sys.argv[1:]:
    c = sqlite3.connect(db)
    for slug, body in (("privacy", ns["PRIVACY"]), ("terms", ns["TERMS"])):
        row = c.execute("select body from cms_pages where slug=?", (slug,)).fetchone()
        if row and row[0].startswith("*[") and "to be supplied by legal" in row[0]:
            c.execute("update cms_pages set body=? where slug=?", (body, slug))
            print(db, slug, "updated")
        else:
            print(db, slug, "left as is" if row else "missing")
    c.commit()
    c.close()
