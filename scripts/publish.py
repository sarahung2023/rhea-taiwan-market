"""Create only public web files; never deploy internal or local trading artifacts."""
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'_site'
if DEST.exists():shutil.rmtree(DEST)
DEST.mkdir()
for name in ('index.html','style.css','app.js'):
    shutil.copy2(ROOT/name,DEST/name)
(DEST/'.nojekyll').write_text('',encoding='utf-8')
d=(DEST/'data');d.mkdir()
for name in ('dashboard.json','status.json','alerts.json'):
    f=ROOT/'data'/name
    if f.exists():shutil.copy2(f,d/name)
print('Static Pages export:', DEST)
