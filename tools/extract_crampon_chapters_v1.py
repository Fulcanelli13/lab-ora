#!/usr/bin/env python3
import hashlib, json, re, unicodedata, urllib.request
from pathlib import Path

SOURCE_URL="https://raw.githubusercontent.com/scrollmapper/bible_databases/e1b254cef86d0e65b1a5d1a94b8b112d0f296a2c/sources/fr/FreCrampon/FreCrampon.json"
SOURCE_COMMIT="e1b254cef86d0e65b1a5d1a94b8b112d0f296a2c"
SOURCE_BLOB_SHA1="d00e7f91c6f20c9e5c6a970deb655bf041dcfdbd"
SOURCE_SIZE=13186190
OUT=Path("data/crampon-rosary-chapters-v1.json")
REPORT=Path("data/crampon-rosary-chapters-v1-report.json")
REQUIRED={
 "Luke":[1,2,3,4,9,15,22,23,24], "John":[1,2,3,6,18,19,20],
 "Matthew":[3,5,6,10,16,17,26,27,28], "Mark":[1,16],
 "1 Corinthians":[11], "Isaias":[53], "Acts":[1,2], "Psalm":[44,131],
 "Canticles":[2,6], "Apocalypse":[11,12], "Judith":[13,15]
}
ALIASES={
 "Luke":["Luke","Luc"], "John":["John","Jean"],
 "Matthew":["Matthew","Matthieu"], "Mark":["Mark","Marc"],
 "1 Corinthians":["1 Corinthians","1 Corinthiens","I Corinthians","Première épître aux Corinthiens","Premiere epitre aux Corinthiens"],
 "Isaias":["Isaiah","Isaias","Isaïe","Isaie","Ésaïe","Esaïe","Esaie"],
 "Acts":["Acts","Actes","Acts of the Apostles","Actes des Apôtres","Actes des Apotres"],
 "Psalm":["Psalm","Psalms","Psaume","Psaumes"],
 "Canticles":["Canticles","Song of Solomon","Song of Songs","Cantique des cantiques","Cantique"],
 "Apocalypse":["Apocalypse","Revelation","Révélation","Revelation of John"],
 "Judith":["Judith"]
}

def norm(s):
 s=unicodedata.normalize("NFKD",str(s)).encode("ascii","ignore").decode("ascii").lower()
 return re.sub(r"[^a-z0-9]+","",s)

def n(v):
 m=re.match(r"\d+",str(v))
 if not m: raise ValueError(v)
 return int(m.group())

def git_blob_sha(data):
 return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()

def main():
 with urllib.request.urlopen(SOURCE_URL,timeout=120) as r: raw=r.read()
 if len(raw)!=SOURCE_SIZE: raise SystemExit(f"source size mismatch {len(raw)} != {SOURCE_SIZE}")
 sha=git_blob_sha(raw)
 if sha!=SOURCE_BLOB_SHA1: raise SystemExit(f"source git blob mismatch {sha} != {SOURCE_BLOB_SHA1}")
 data=json.loads(raw.decode("utf-8"))
 books=data.get("books") if isinstance(data,dict) else None
 if not isinstance(books,list): raise SystemExit(f"unexpected schema: {type(data)} / {list(data) if isinstance(data,dict) else ''}")
 bynorm={norm(b.get("name")):b for b in books}
 resolved={}
 for canonical,candidates in ALIASES.items():
  hit=next((bynorm[norm(a)] for a in candidates if norm(a) in bynorm),None)
  if not hit: raise SystemExit(f"cannot resolve {canonical}; source books={[b.get('name') for b in books]}")
  resolved[canonical]=hit
 out={}
 source_blanks=[]
 for canonical, chapters in REQUIRED.items():
  source=resolved[canonical]
  source_ch={n(c.get("chapter")):c for c in source.get("chapters",[])}
  out[canonical]={}
  for ch in chapters:
   if ch not in source_ch: raise SystemExit(f"missing chapter {canonical} {ch}")
   verses=[]
   for v in source_ch[ch].get("verses",[]):
    verse_no=n(v.get("verse"))
    text=str(v.get("text","")).strip()
    if not text:
     source_blanks.append(f"{canonical} {ch}:{verse_no}")
     continue
    verses.append({"verse":verse_no,"text":text})
   verses.sort(key=lambda x:x["verse"])
   if not verses: raise SystemExit(f"empty chapter {canonical} {ch}")
   out[canonical][str(ch)]=verses
 meta={
  "translation":"La Bible Augustin Crampon 1923","language":"fr",
  "source_repository":"scrollmapper/bible_databases","source_path":"sources/fr/FreCrampon/FreCrampon.json",
  "source_commit":SOURCE_COMMIT,"source_git_blob_sha1":SOURCE_BLOB_SHA1,"source_bytes":SOURCE_SIZE,
  "source_verified":True,"required_book_count":len(REQUIRED),"required_chapter_count":sum(map(len,REQUIRED.values())),
  "source_book_names":{k:v.get("name") for k,v in resolved.items()},"blank_source_entries":source_blanks
 }
 payload={"metadata":meta,"chapters":out}
 OUT.parent.mkdir(parents=True,exist_ok=True)
 OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 REPORT.write_text(json.dumps({"status":"PASS_WITH_SOURCE_GAPS" if source_blanks else "PASS",**meta},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(json.dumps({"status":"PASS_WITH_SOURCE_GAPS" if source_blanks else "PASS",**meta},ensure_ascii=False,indent=2))

if __name__=="__main__": main()
