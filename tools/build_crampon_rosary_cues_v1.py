#!/usr/bin/env python3
import json, re
from pathlib import Path

CORPUS=Path('data/crampon-rosary-chapters-v1.json')
CONTRACT=Path('data/rosary-scripture-reference-contract-v1.json')
REPORT=Path('data/crampon-rosary-cues-v1-report.json')
CUE_DIR=Path('data/crampon-cues')
CHAPTER_DIR=Path('data/crampon-chapters')

SPLITS={
 'Luke 1:38a':'Voici la servante du Seigneur,',
 'Luke 1:38b':"qu'il me soit fait selon votre parole.",
 'Luke 3:21a':'Jésus fut aussi baptisé',
 'Luke 3:21b':"Jésus fut aussi baptisé, et pendant qu'il priait, le ciel s'ouvrit,",
 'Luke 3:22a':"et l'Esprit-Saint descendit sur lui sous une forme corporelle, comme une colombe,",
 'Luke 3:22b':"Tu es mon Fils bien-aimé; en toi j'ai mes complaisances.",
 'Matthew 27:29a':"Ils tressèrent une couronne d'épines, qu'ils posèrent sur sa tête, et lui mirent un roseau dans la main droite;",
 'Matthew 27:29b':'puis, fléchissant le genou devant lui, ils lui disaient par dérision: " Salut, roi des Juifs. "'
}
FAMILY={'joy':'joyful','lum':'luminous','sor':'sorrowful','glo':'glorious'}
SLUGS={'1 Corinthians':'1-corinthians','Isaias':'isaias','Psalm':'psalm','Canticles':'canticles','Apocalypse':'apocalypse','Judith':'judith','Luke':'luke','John':'john','Matthew':'matthew','Mark':'mark','Acts':'acts'}
REF_RE=re.compile(r'^(.+?) (\d+):(\d+)(?:[–-](\d+))?([ab])?$')

def verse_map(corpus,book,chapter):
 try: rows=corpus['chapters'][book][str(chapter)]
 except KeyError: raise SystemExit(f'missing chapter {book} {chapter}')
 return {int(v['verse']):v['text'] for v in rows if str(v.get('text','')).strip()}

def parse_ref(ref):
 m=REF_RE.match(ref)
 if not m: raise SystemExit(f'malformed reference: {ref}')
 book,chapter,start,end,suffix=m.groups()
 return book,int(chapter),int(start),int(end or start),suffix

def main():
 corpus=json.loads(CORPUS.read_text(encoding='utf-8'))
 contract=json.loads(CONTRACT.read_text(encoding='utf-8'))
 if len(contract)!=200: raise SystemExit(f'contract count {len(contract)} != 200')
 seen=set(); out={v:[] for v in FAMILY.values()}; split_checks=[]; missing=[]
 for row in contract:
  key=(row['m'],int(row['b']))
  if key in seen: raise SystemExit(f'duplicate cue {key}')
  seen.add(key)
  ref=row['r']; book,ch,start,end,suffix=parse_ref(ref); vm=verse_map(corpus,book,ch)
  need=list(range(start,end+1)); absent=[v for v in need if not vm.get(v)]
  if absent:
   missing.append({'reference':ref,'missing_verses':absent}); continue
  source=' '.join(vm[v] for v in need)
  if suffix:
   if ref not in SPLITS: raise SystemExit(f'unconfigured split {ref}')
   fr=SPLITS[ref]
   full=vm[start]
   if fr not in full: raise SystemExit(f'split is not verbatim substring: {ref} => {fr!r} not in {full!r}')
   policy='verbatim_source_segment'
   split_checks.append({'reference':ref,'source_verse':full,'segment':fr,'verbatim_substring':True})
  else:
   fr=source; policy='verbatim_full_referenced_verses'
  fam=FAMILY[row['m'][:3]]
  out[fam].append({'m':row['m'],'b':int(row['b']),'r':ref,'fr':fr,'policy':policy,'source_verses':need})
 if missing: raise SystemExit('missing referenced verses: '+json.dumps(missing,ensure_ascii=False))
 CUE_DIR.mkdir(parents=True,exist_ok=True); CHAPTER_DIR.mkdir(parents=True,exist_ok=True)
 for fam,rows in out.items():
  if len(rows)!=50: raise SystemExit(f'{fam} count {len(rows)} != 50')
  payload={'metadata':{'translation':'La Bible Augustin Crampon 1923','source_git_blob_sha1':corpus['metadata']['source_git_blob_sha1'],'family':fam,'cue_count':50},'cues':rows}
  (CUE_DIR/f'{fam}.json').write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
 for book,chapters in corpus['chapters'].items():
  payload={'metadata':{'translation':'La Bible Augustin Crampon 1923','source_git_blob_sha1':corpus['metadata']['source_git_blob_sha1'],'book':book},'chapters':chapters}
  (CHAPTER_DIR/f'{SLUGS[book]}.json').write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
 report={
  'status':'PASS','translation':'La Bible Augustin Crampon 1923','source_git_blob_sha1':corpus['metadata']['source_git_blob_sha1'],
  'contract_count':len(contract),'validated_cue_count':sum(len(v) for v in out.values()),'family_counts':{k:len(v) for k,v in out.items()},
  'split_cue_count':len(split_checks),'split_checks':split_checks,'chapter_count':sum(len(v) for v in corpus['chapters'].values()),
  'book_count':len(corpus['chapters']),'blank_source_entries':corpus['metadata'].get('blank_source_entries',[]),
  'fail_closed':True,'text_policy':'No model translation. Ordinary cues are exact full Crampon referenced verses; a/b cues are exact source substrings.'
 }
 REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
