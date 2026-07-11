from __future__ import annotations
from pathlib import Path
import json,re,os
import httpx
from pypdf import PdfReader

DOI_RE=re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
PMID_RE=re.compile(r"PMID[:\s]*(\d{6,10})",re.I)
YEAR_RE=re.compile(r"\b(19\d{2}|20\d{2})\b")
MECH={
"PI3K/AKT":["pi3k","akt"],"Nrf2":["nrf2","nfe2l2","ho-1"],"MAPK":["mapk","erk","jnk","p38"],
"NF-κB":["nf-κb","nf-kb"],"氧化应激":["oxidative stress","reactive oxygen"," ros ","mda","sod"],
"炎症":["inflammation","tnf-α","il-6","il-1β"],"凋亡":["apoptosis","bax","bcl-2","caspase"],
"缺血性脑卒中":["ischemic stroke","cerebral ischemia","oxygen-glucose deprivation","ogd"],
"铁死亡":["ferroptosis","gpx4","slc7a11"],"自噬":["autophagy","lc3","beclin"]}

def safe_name(s):
 return ''.join('_' if c in '<>:"/\\|?*\0' else c for c in s.strip()).replace(' ','_')[:180] or 'untitled'
def extract_text(path,max_pages=20,max_chars=90000):
 r=PdfReader(str(path)); out=[]
 for pg in r.pages[:max_pages]:
  out.append(pg.extract_text() or '')
  if sum(map(len,out))>=max_chars: break
 return '\n\n'.join(out)[:max_chars]
def detect(text,fallback):
 lines=[x.strip() for x in text.splitlines() if x.strip()]
 doi=(DOI_RE.search(text).group(0).rstrip('.,;:)') if DOI_RE.search(text) else '')
 pmid=(PMID_RE.search(text).group(1) if PMID_RE.search(text) else '')
 year=(YEAR_RE.search(text).group(1) if YEAR_RE.search(text) else '')
 title=fallback
 for line in lines[:60]:
  low=line.lower()
  if 25<=len(line)<=240 and not low.startswith(('abstract','keywords','doi','pmid','contents lists available','www.','http','received','accepted')):
   if sum(c.isalpha() for c in line)/max(len(line),1)>.55: title=line; break
 return {'title':title,'doi':doi,'pmid':pmid,'year':year}
def crossref(doi):
 if not doi:return {}
 try:
  r=httpx.get(f'https://api.crossref.org/works/{doi}',timeout=15,headers={'User-Agent':'XianYuResearchOS/1.0'});r.raise_for_status();m=r.json()['message']
  authors=[' '.join([a.get('given',''),a.get('family','')]).strip() for a in m.get('author',[]) if a]
  year=''
  for k in ('published-print','published-online','issued'):
   d=m.get(k,{}).get('date-parts',[])
   if d and d[0]: year=str(d[0][0]);break
  return {'title':(m.get('title') or [''])[0],'authors':authors,'journal':(m.get('container-title') or [''])[0],'year':year,'doi':m.get('DOI',doi),'abstract':m.get('abstract','') or ''}
 except Exception:return {}
def pubmed(pmid):
 if not pmid:return {}
 try:
  r=httpx.get('https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi',params={'db':'pubmed','id':pmid,'retmode':'json'},timeout=15);r.raise_for_status();d=r.json()['result'][str(pmid)]
  doi=''
  for a in d.get('articleids',[]):
   if a.get('idtype')=='doi': doi=a.get('value','');break
  return {'title':d.get('title',''),'authors':[a.get('name','') for a in d.get('authors',[]) if a.get('name')],'journal':d.get('fulljournalname') or d.get('source',''),'year':d.get('pubdate','')[:4],'doi':doi,'pmid':pmid}
 except Exception:return {}
def classify(text):
 low=text.lower(); tags=[k for k,v in MECH.items() if any(t.lower() in low for t in v)]
 use=[]
 if any(k in low for k in ['review','background','epidemiology','pathogenesis']):use.append('Introduction')
 if any(k in low for k in ['mechanism','pathway','limitation','consistent with','in contrast']):use.append('Discussion')
 if any(k in low for k in ['method','protocol','assay','western blot','rt-qpcr']):use.append('Methods')
 if any(k in low for k in ['target','network pharmacology','ppi','kegg','go enrichment']):use.append('Network Pharmacology')
 if any(k in low for k in ['geo','transcriptome','rna-seq','differentially expressed']):use.append('Gene / Omics')
 if any(k in low for k in ['molecular docking','binding energy','molecular dynamics']):use.append('Docking / MD')
 return tags,use
def ai_read(text,context):
 base=os.getenv('AI_API_BASE','').rstrip('/');key=os.getenv('AI_API_KEY','');model=os.getenv('AI_MODEL','')
 prompt=f"""课题背景：{context}\n请严格基于论文文本，以JSON输出：one_sentence_summary,background,objective,methods,main_results,innovation,limitations,research_gap,project_relevance,introduction_material,discussion_material,recommended_targets,recommended_pathways,recommended_experiments,confidence_notes。\n论文文本：\n{text[:24000]}"""
 if not(base and key and model): return {'status':'not_configured','prompt':prompt}
 try:
  payload={'model':model,'messages':[{'role':'system','content':'你是生物医药科研文献分析助手。不得虚构。只输出合法JSON。'},{'role':'user','content':prompt}],'temperature':0.1}
  r=httpx.post(base+'/chat/completions',headers={'Authorization':f'Bearer {key}'},json=payload,timeout=120);r.raise_for_status();c=r.json()['choices'][0]['message']['content']
  try:return json.loads(c)
  except:return {'status':'raw','raw':c}
 except Exception as e:return {'status':'error','error':str(e),'prompt':prompt}
def save(root,rec):
 pdf=root/'04_文献笔记'/'PDF库';db=root/'04_文献笔记'/'文献数据库';cards=root/'04_文献笔记'/'V2卡片'
 for d in (pdf,db,cards):d.mkdir(parents=True,exist_ok=True)
 stem=safe_name(Path(rec['source_pdf']).stem)
 (db/f'{stem}.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2),encoding='utf-8')
 title=safe_name(rec.get('title') or stem)
 ai=rec.get('ai_summary') or {}
 def f(k):
  v=ai.get(k,''); return '\n'.join('- '+str(x) for x in v) if isinstance(v,list) else str(v)
 md=f"""# 文献卡片 V2｜{rec.get('title','')}\n\n## 基础信息\n- 作者：{'; '.join(rec.get('authors',[]))}\n- 期刊：{rec.get('journal','')}\n- 年份：{rec.get('year','')}\n- DOI：{rec.get('doi','')}\n- PMID：{rec.get('pmid','')}\n- 来源 PDF：{rec.get('source_pdf','')}\n\n## 机制标签\n{', '.join(rec.get('mechanism_tags',[]))}\n\n## 推荐用途\n{', '.join(rec.get('usage_tags',[]))}\n\n## 一句话总结\n{f('one_sentence_summary')}\n\n## 研究背景\n{f('background')}\n\n## 研究目的\n{f('objective')}\n\n## 方法\n{f('methods')}\n\n## 主要结果\n{f('main_results')}\n\n## 创新点\n{f('innovation')}\n\n## 局限性\n{f('limitations')}\n\n## Research Gap\n{f('research_gap')}\n\n## 与当前课题关系\n{f('project_relevance')}\n\n## Introduction 素材\n{f('introduction_material')}\n\n## Discussion 素材\n{f('discussion_material')}\n\n## 推荐靶点\n{f('recommended_targets')}\n\n## 推荐通路\n{f('recommended_pathways')}\n\n## 推荐实验\n{f('recommended_experiments')}\n\n## 可信度与注意事项\n{f('confidence_notes')}\n"""
 (cards/f'{title}.md').write_text(md,encoding='utf-8')
 return db/f'{stem}.json'
def load(root,source_pdf):
 p=root/'04_文献笔记'/'文献数据库'/f'{safe_name(Path(source_pdf).stem)}.json'
 return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None
def bibtex(rec):
 key=f"{rec.get('year') or 'nd'}_{(rec.get('authors') or ['unknown'])[0].split()[-1]}";authors=' and '.join(rec.get('authors',[]))
 return f"@article{{{key},\n  title = {{{rec.get('title','')}}},\n  author = {{{authors}}},\n  journal = {{{rec.get('journal','')}}},\n  year = {{{rec.get('year','')}}},\n  doi = {{{rec.get('doi','')}}},\n  pmid = {{{rec.get('pmid','')}}}\n}}"
def ris(rec):
 out=['TY  - JOUR',f"TI  - {rec.get('title','')}",f"JO  - {rec.get('journal','')}",f"PY  - {rec.get('year','')}",f"DO  - {rec.get('doi','')}",f"AN  - {rec.get('pmid','')}"]
 out += [f'AU  - {a}' for a in rec.get('authors',[])];out.append('ER  -');return '\n'.join(out)
