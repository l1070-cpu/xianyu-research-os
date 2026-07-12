from pathlib import Path
from fastapi import APIRouter,Form,UploadFile,File,HTTPException,Request
from fastapi.responses import HTMLResponse,RedirectResponse,FileResponse,PlainTextResponse
from fastapi.templating import Jinja2Templates
from .core import *
router=APIRouter(prefix='/literature-v2',tags=['literature-v2'])
ROOT=Path(__file__).resolve().parents[4]
PDF=ROOT/'04_文献笔记'/'PDF库';PDF.mkdir(parents=True,exist_ok=True)
templates = Jinja2Templates(directory=[
    str(Path(__file__).resolve().parent / "templates"),
    str(Path(__file__).resolve().parents[1] / "templates"),
])
CTX='金毛狗脊治疗缺血性脑卒中；UPLC-QTOF/MS、网络药理、Gene/Omics、虚拟筛选、分子对接、MD、ADMET、H/R细胞模型、WB、RT-qPCR。'
def valid(path):
 p=(ROOT/path).resolve()
 if PDF.resolve() not in p.parents: raise HTTPException(403,'非法路径')
 return p
@router.get('',response_class=HTMLResponse)
def index(request:Request):
 items=[]
 for p in sorted(PDF.glob('*.pdf'),key=lambda x:x.stat().st_mtime,reverse=True):
  rel=str(p.relative_to(ROOT));items.append({'name':p.name,'path':rel,'record':load(ROOT,rel)})
 return templates.TemplateResponse(request=request,name='index.html',context={'items':items})
@router.post('/upload')
async def upload(file:UploadFile=File(...)):
 if not file.filename or not file.filename.lower().endswith('.pdf'):raise HTTPException(400,'仅支持PDF')
 (PDF/safe_name(file.filename)).write_bytes(await file.read());return RedirectResponse('/literature-v2',303)
@router.get('/pdf')
def open_pdf(path:str):
 p=valid(path)
 if not p.exists():raise HTTPException(404,'PDF不存在')
 return FileResponse(p,media_type='application/pdf',filename=p.name)
@router.post('/analyze')
def analyze(path:str=Form(...)):
 p=valid(path);text=extract_text(p);base=detect(text,p.stem);meta=crossref(base['doi']) if base['doi'] else {};pm=pubmed(base['pmid']) if base['pmid'] else {}
 for k,v in pm.items():
  if v and not meta.get(k):meta[k]=v
 tags,use=classify(text)
 rec={'source_pdf':str(p.relative_to(ROOT)),'title':meta.get('title') or base['title'],'authors':meta.get('authors',[]),'journal':meta.get('journal',''),'year':meta.get('year') or base['year'],'doi':meta.get('doi') or base['doi'],'pmid':meta.get('pmid') or base['pmid'],'abstract':meta.get('abstract',''),'mechanism_tags':tags,'usage_tags':use,'ai_summary':{},'raw_text_preview':text[:12000]}
 save(ROOT,rec);return RedirectResponse('/literature-v2/item?path='+rec['source_pdf'],303)
@router.get('/item',response_class=HTMLResponse)
def item(request:Request,path:str):
 rec=load(ROOT,path)
 if not rec:raise HTTPException(404,'尚未分析')
 return templates.TemplateResponse(request=request,name='detail.html',context={'record':rec})
@router.post('/ai-read')
def ai(path:str=Form(...)):
 rec=load(ROOT,path)
 if not rec:raise HTTPException(404,'记录不存在')
 rec['ai_summary']=ai_read(extract_text(valid(path)),CTX);save(ROOT,rec);return RedirectResponse('/literature-v2/item?path='+path,303)
@router.get('/export/bibtex')
def eb(path:str):
 rec=load(ROOT,path)
 if not rec:raise HTTPException(404,'记录不存在')
 return PlainTextResponse(bibtex(rec),headers={'Content-Disposition':'attachment; filename=reference.bib'})
@router.get('/export/ris')
def er(path:str):
 rec=load(ROOT,path)
 if not rec:raise HTTPException(404,'记录不存在')
 return PlainTextResponse(ris(rec),headers={'Content-Disposition':'attachment; filename=reference.ris'})
