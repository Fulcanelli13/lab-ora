#!/usr/bin/env python3
import hashlib, json, re, unicodedata, urllib.request
from pathlib import Path

PINNED_COMMIT='e1b254cef86d0e65b1a5d1a94b8b112d0f296a2c'
EXPECTED_BLOB='d00e7f91c6f20c9e5c6a970deb655bf041dcfdbd'
SOURCE_SIZE=13186190
SOURCE_URL=f'https://raw.githubusercontent.com/scrollmapper/bible_databases/{PINNED_COMMIT}/sources/fr/FreCrampon/FreCrampon.json'
REFS_PATH=Path('tools/rosary_refs_en.json')
OUT_PATH=Path('data/rosary-scripture-fr-crampon-v1.json')
AUDIT_PATH=Path('data/rosary-scripture-fr-crampon-v1-audit.json')

ALIASES={
 'Luke':['Luke','Luc'],'John':['John','Jean'],'Matthew':['Matthew','Matthieu'],'Mark':['Mark','Marc'],
 '1 Corinthians':['1 Corinthians','I Corinthians','1 Corinthiens','Première épître aux Corinthiens'],
 'Isaias':['Isaiah','Isaias','Isaïe','Isaie','Ésaïe','Esaie'],'Acts':['Acts','Actes','Acts of the Apostles'],
 'Psalm':['Psalm','Psalms','Psaume','Psaumes'],'Canticles':['Canticles','Song of Solomon','Song of Songs','Cantique des cantiques'],
 'Apocalypse':['Apocalypse','Revelation','Revelation of John'],'Judith':['Judith']
}
PSALM_CHAPTER_ALIAS={44:45,131:132}

def norm(s):
 s=unicodedata.normalize('NFKD',str(s)).encode('ascii','ignore').decode('ascii').lower()
 return re.sub(r'[^a-z0-9]+','',s)

def git_blob_sha(data):
 return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()

def parse_ref(ref):
 m=re.fullmatch(r'(.+?)\s+(\d+):(\d+)([ab])?(?:[–-](\d+))?',ref.strip())
 if not m: raise ValueError(f'Unsupported reference: {ref}')
 book,ch,v1,suffix,v2=m.groups(); return book,int(ch),int(v1),suffix,int(v2 or v1)

def slice_between(text,start,end=None):
 i=text.find(start)
 if i<0: raise ValueError(f'start marker not found: {start!r}')
 j=len(text) if end is None else text.find(end,i+len(start))
 if end is not None and j<0: raise ValueError(f'end marker not found: {end!r}')
 return text[i:j].strip()

def special_segment(book,ch,v,suffix,text):
 key=(book,ch,v,suffix)
 rules={
  ('Luke',1,38,'a'):("Marie dit alors: \" Voici la servante du Seigneur,"," qu'il me soit fait"),
  ('Luke',1,38,'b'):("qu'il me soit fait selon votre parole."," \" Et l'ange"),
  ('Luke',3,21,'a'):("Jésus fut aussi baptisé",", et pendant"),
  ('Luke',3,21,'b'):("Jésus fut aussi baptisé, et pendant qu'il priait, le ciel s'ouvrit,",None),
  ('Luke',3,22,'a'):("et l'Esprit-Saint descendit sur lui sous une forme corporelle, comme une colombe,"," et du ciel"),
  ('Luke',3,22,'b'):("Tu es mon Fils bien-aimé; en toi j'ai mes complaisances."," \""),
  ('Matthew',27,29,'a'):("Ils tressèrent une couronne d'épines, qu'ils posèrent sur sa tête, et lui mirent un roseau dans la main droite;"," puis,"),
  ('Matthew',27,29,'b'):("fléchissant le genou devant lui, ils lui disaient par dérision: \" Salut, roi des Juifs. \"",None),
 }
 if key not in rules: raise ValueError(f'No split rule for {key}')
 a,b=rules[key]; return slice_between(text,a,b)

def judith_13_virtual(verse,blob):
 rules={
  23:("Ozias, le prince du peuple d'Israël, lui dit: \" Ma fille, tu es bénie par le Seigneur, le Dieu très haut, plus que toutes les femmes qui sont sur la terre."," Béni soit le Seigneur"),
  25:("Il a rendu aujourd'hui ton nom si glorieux, que ta louange ne disparaîtra pas de la bouche des hommes, qui se souviendront éternellement de la puissance du Seigneur; car, en leur faveur, tu n'as pas épargné ta vie en voyant les souffrances et la détresse de ta race, mais tu nous a sauvés de la ruine en marchant dans la droiture en présence de notre Dieu."," \" Et tout le peuple")
 }
 if verse not in rules: return None
 a,b=rules[verse]; return slice_between(blob,a,b)

def main():
 specs=json.loads(REFS_PATH.read_text('utf-8'))['refs']
 with urllib.request.urlopen(SOURCE_URL,timeout=120) as r: raw=r.read()
 if len(raw)!=SOURCE_SIZE: raise SystemExit(f'source size mismatch {len(raw)} != {SOURCE_SIZE}')
 actual=git_blob_sha(raw)
 if actual!=EXPECTED_BLOB: raise SystemExit(f'blob mismatch {actual} != {EXPECTED_BLOB}')
 corpus=json.loads(raw.decode('utf-8'))
 books=corpus.get('books',[]); bynorm={norm(b.get('name')):b for b in books}; resolved={}
 for canonical,candidates in ALIASES.items():
  hit=next((bynorm[norm(a)] for a in candidates if norm(a) in bynorm),None)
  if not hit: raise SystemExit(f'cannot resolve {canonical}')
  resolved[canonical]=hit

 out=[]; missing=[]; used_chapters=set(); split_count=0; virtual_count=0
 for spec in specs:
  book,ch,v1,suffix,v2=parse_ref(spec['r']); source_ch=PSALM_CHAPTER_ALIAS.get(ch,ch) if book=='Psalm' else ch
  used_chapters.add((book,source_ch)); srcbook=resolved[book]
  chapter=next((c for c in srcbook.get('chapters',[]) if int(re.match(r'\d+',str(c.get('chapter'))).group())==source_ch),None)
  if not chapter:
   missing.append({'spec':spec,'reason':'chapter'}); continue
  verses={int(re.match(r'\d+',str(v.get('verse'))).group()):str(v.get('text','')).strip() for v in chapter.get('verses',[]) if re.match(r'\d+',str(v.get('verse')))}
  try:
   if book=='Judith' and ch==13 and v1==v2 and v1 in (23,25):
    blob=verses.get(20,''); full=judith_13_virtual(v1,blob); virtual_count+=1
   else:
    absent=[v for v in range(v1,v2+1) if not verses.get(v)]
    if absent: raise KeyError(f'missing verses {absent}')
    full=' '.join(verses[v] for v in range(v1,v2+1)).strip()
   if suffix:
    full=special_segment(book,ch,v1,suffix,full); split_count+=1
   if not full: raise ValueError('empty excerpt')
  except Exception as e:
   missing.append({'spec':spec,'reason':'extract','detail':str(e)}); continue
  out.append({
   'mystery_id':spec['m'],'bead':spec['b'],'reference':spec['r'],'display_excerpt':full,
   'edition':'La Bible Augustin Crampon 1923','display_edition_label':'Crampon 1923','cue_type':'scripture',
   'language':'fr','text_policy':'verbatim source excerpt','verification_status':'source_locked',
   'source':{'repository':'scrollmapper/bible_databases','commit':PINNED_COMMIT,'path':'sources/fr/FreCrampon/FreCrampon.json','git_blob_sha':EXPECTED_BLOB}
  })

 audit={'schema':'labora.rosary.crampon.audit.v1','status':'PASS' if len(out)==200 and not missing else 'FAIL',
  'source_commit':PINNED_COMMIT,'source_git_blob_sha':actual,'source_bytes':len(raw),'input_cues':len(specs),'output_cues':len(out),
  'missing':missing,'source_chapters_used':len(used_chapters),'split_segments':split_count,'judith_virtual_verses':virtual_count,
  'psalm_numbering_aliases':{'Psalm 44':'Psalms 45','Psalm 131':'Psalms 132'}}
 OUT_PATH.parent.mkdir(parents=True,exist_ok=True)
 OUT_PATH.write_text(json.dumps({'schema':'labora.rosary.scripture.fr.crampon.v1','count':len(out),'cues':out},ensure_ascii=False,indent=2)+'\n','utf-8')
 AUDIT_PATH.write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n','utf-8')
 print(json.dumps(audit,ensure_ascii=False,indent=2))
 if audit['status']!='PASS': raise SystemExit('Crampon cue extraction failed')

if __name__=='__main__': main()
