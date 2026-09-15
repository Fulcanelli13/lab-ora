#!/usr/bin/env python3
import json
from pathlib import Path
SRC=Path('data/rosary-scripture-fr-crampon-v1.json')
OUT=Path('data/rosary-scripture-fr-crampon-v1.compact.json')
raw=json.loads(SRC.read_text('utf-8'))
by={}
for c in raw['cues']:
    by.setdefault(c['mystery_id'],[None]*10)[int(c['bead'])-1]=c['display_excerpt']
expected=['joy1','joy2','joy3','joy4','joy5','lum1','lum2','lum3','lum4','lum5','sor1','sor2','sor3','sor4','sor5','glo1','glo2','glo3','glo4','glo5']
missing=[]
for mid in expected:
    arr=by.get(mid)
    if not arr or len(arr)!=10 or any(not x for x in arr): missing.append(mid)
if missing: raise SystemExit('Incomplete compact dataset: '+','.join(missing))
out={
 'schema':'labora.rosary.scripture.fr.crampon.compact.v1',
 'count':200,
 'edition':'La Bible Augustin Crampon 1923',
 'source':{'repository':'scrollmapper/bible_databases','commit':'e1b254cef86d0e65b1a5d1a94b8b112d0f296a2c','git_blob_sha':'d00e7f91c6f20c9e5c6a970deb655bf041dcfdbd'},
 'cues':{mid:by[mid] for mid in expected}
}
OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n','utf-8')
print(f'compact cues: {sum(len(v) for v in by.values())}; bytes={OUT.stat().st_size}')
