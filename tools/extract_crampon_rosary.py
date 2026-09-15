#!/usr/bin/env python3
import hashlib, json, re, urllib.request
from pathlib import Path

PINNED_COMMIT = 'e1b254cef86d0e65b1a5d1a94b8b112d0f296a2c'
EXPECTED_BLOB = 'd00e7f91c6f20c9e5c6a970deb655bf041dcfdbd'
SOURCE_URL = f'https://raw.githubusercontent.com/scrollmapper/bible_databases/{PINNED_COMMIT}/sources/fr/FreCrampon/FreCrampon.json'
REFS_PATH = Path('tools/rosary_refs_en.json')
OUT_PATH = Path('data/rosary-scripture-fr-crampon.json')
AUDIT_PATH = Path('data/rosary-scripture-fr-crampon-audit.json')

BOOK_ALIASES = {
    '1 Corinthians':['1 Corinthians','I Corinthians','1 Corinthians.','First Corinthians'],
    'Acts':['Acts','Acts of the Apostles'],
    'Apocalypse':['Apocalypse','Revelation','Revelation of John'],
    'Canticles':['Canticles','Song of Solomon','Song of Songs'],
    'Isaias':['Isaias','Isaiah'],
    'John':['John','Gospel of John'],
    'Judith':['Judith'],
    'Luke':['Luke','Gospel of Luke'],
    'Mark':['Mark','Gospel of Mark'],
    'Matthew':['Matthew','Gospel of Matthew'],
    'Psalm':['Psalm','Psalms'],
}

def norm(s):
    return re.sub(r'[^a-z0-9]+','',str(s).lower())

def git_blob_sha(data: bytes):
    return hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest()

def parse_ref(ref):
    m=re.fullmatch(r'(.+?)\s+(\d+):(\d+)([ab])?(?:[–-](\d+))?',ref.strip())
    if not m: raise ValueError(f'Unsupported reference: {ref}')
    book, ch, v1, suffix, v2 = m.groups()
    return book, int(ch), int(v1), suffix, int(v2 or v1)

def main():
    specs=json.loads(REFS_PATH.read_text('utf-8'))['refs']
    with urllib.request.urlopen(SOURCE_URL, timeout=90) as r:
        raw=r.read()
    actual=git_blob_sha(raw)
    if actual != EXPECTED_BLOB:
        raise SystemExit(f'Pinned Crampon blob mismatch: expected {EXPECTED_BLOB}, got {actual}')
    corpus=json.loads(raw.decode('utf-8-sig'))
    books=corpus.get('books',[])
    by_norm={norm(b.get('name')): b for b in books}
    resolved={}
    unresolved=[]
    for requested, aliases in BOOK_ALIASES.items():
        b=None
        for a in aliases:
            b=by_norm.get(norm(a))
            if b: break
        if b: resolved[requested]=b
        else: unresolved.append(requested)
    if unresolved:
        print('Available books:', [b.get('name') for b in books])
        raise SystemExit('Unresolved source books: '+', '.join(unresolved))

    out=[]; missing=[]; suffix_items=[]; required_chapters=set()
    for spec in specs:
        book,ch,v1,suffix,v2=parse_ref(spec['r'])
        required_chapters.add((book,ch))
        srcbook=resolved.get(book) or by_norm.get(norm(book))
        if not srcbook:
            missing.append({'spec':spec,'reason':'book'}); continue
        chapter=next((c for c in srcbook.get('chapters',[]) if int(c.get('chapter'))==ch),None)
        if not chapter:
            missing.append({'spec':spec,'reason':'chapter'}); continue
        verses={int(v.get('verse')): str(v.get('text','')).strip() for v in chapter.get('verses',[])}
        absent=[v for v in range(v1,v2+1) if v not in verses or not verses[v]]
        if absent:
            missing.append({'spec':spec,'reason':'verse','absent':absent}); continue
        full=' '.join(verses[v] for v in range(v1,v2+1)).strip()
        item={
          'mystery_id':spec['m'],'bead':spec['b'],'reference':spec['r'],
          'display_excerpt':full if not suffix else None,
          'edition':'La Bible Augustin Crampon 1923',
          'display_edition_label':'Crampon 1923','language':'fr',
          'text_policy':'verbatim verse span from pinned source',
          'verification_status':'source_locked_full_span' if not suffix else 'source_locked_manual_segment_required',
          'source':{'repository':'scrollmapper/bible_databases','commit':PINNED_COMMIT,'path':'sources/fr/FreCrampon/FreCrampon.json','git_blob_sha':EXPECTED_BLOB},
        }
        if suffix:
            item['source_full_verse']=full
            item['segment']=suffix
            suffix_items.append({'mystery_id':spec['m'],'bead':spec['b'],'reference':spec['r'],'source_full_verse':full})
        out.append(item)

    audit={
      'schema':'labora.rosary.crampon.audit.v1',
      'source_url':SOURCE_URL,'source_commit':PINNED_COMMIT,'source_git_blob_sha':actual,
      'input_cues':len(specs),'output_cues':len(out),'missing':missing,
      'required_chapters':len(required_chapters),'suffix_segments_pending':suffix_items,
      'available_book_count':len(books),
    }
    OUT_PATH.parent.mkdir(parents=True,exist_ok=True)
    OUT_PATH.write_text(json.dumps({'schema':'labora.rosary.scripture.fr.crampon.v1','count':len(out),'cues':out},ensure_ascii=False,indent=2)+'\n','utf-8')
    AUDIT_PATH.write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n','utf-8')
    if missing or len(out)!=200:
        raise SystemExit(f'Extraction incomplete: {len(out)}/200; missing={len(missing)}')
    print(f'Extracted {len(out)}/200 cues across {len(required_chapters)} chapters; {len(suffix_items)} manual a/b segments pending.')

if __name__=='__main__': main()
