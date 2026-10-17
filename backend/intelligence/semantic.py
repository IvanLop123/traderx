"""Source-quoted semantic evidence; all numerical aggregation stays local."""
import hashlib
from datetime import datetime,timedelta
from typing import Literal
from pydantic import Field
from backend.schemas.contracts import Contract,Feature,AssetIdentifier,now

class Relationship(Contract):
    subject:str=Field(min_length=1,max_length=120)
    relation:Literal['supplies','customer_of','depends_on','constrained_by','competes_with','mitigates']
    object:str=Field(min_length=1,max_length=120)
    quote:str=Field(min_length=1,max_length=1200)

class Bottleneck(Contract):
    company:str=Field(min_length=1,max_length=120)
    type:str=Field(min_length=1,max_length=100)
    severity:Literal['low','medium','high','unknown']='unknown'
    duration:str|None=Field(default=None,max_length=200)
    product:str|None=Field(default=None,max_length=200)
    affected_revenue:str|None=Field(default=None,max_length=200)
    mitigation:str|None=Field(default=None,max_length=400)
    quote:str=Field(min_length=1,max_length=1200)

class AnswerAssessment(Contract):
    question_quote:str=Field(min_length=1,max_length=1200)
    answer_quote:str=Field(min_length=1,max_length=1200)
    question_topic:str=Field(max_length=120)
    answer_topic:str=Field(max_length=120)
    similarity:float|None=Field(default=None,ge=0,le=1)
    directness:float|None=Field(default=None,ge=0,le=1)
    specificity:float|None=Field(default=None,ge=0,le=1)
    skepticism:float|None=Field(default=None,ge=0,le=1)
    disagreement:float|None=Field(default=None,ge=0,le=1)
    core_answered:bool|None=None
    followup_needed:bool|None=None
    concern:str|None=Field(default=None,max_length=500)

class Contradiction(Contract):
    first_quote:str=Field(min_length=1,max_length=1200)
    second_quote:str=Field(min_length=1,max_length=1200)
    explanation:str=Field(max_length=600)

class SourceComparison(Contract):
    relation:Literal['confirms','updates','contradicts','new_claim']
    prior_quote:str|None=Field(default=None,min_length=1,max_length=1200)
    current_quote:str=Field(min_length=1,max_length=1200)
    explanation:str=Field(min_length=1,max_length=600)

class SemanticResearch(Contract):
    relationships:list[Relationship]=Field(default_factory=list,max_length=8)
    bottlenecks:list[Bottleneck]=Field(default_factory=list,max_length=8)
    answers:list[AnswerAssessment]=Field(default_factory=list,max_length=8)
    contradictions:list[Contradiction]=Field(default_factory=list,max_length=8)
    comparisons:list[SourceComparison]=Field(default_factory=list,max_length=4)

PROMPT = (' Optionally add "research" containing arrays relationships, bottlenecks, answers, contradictions. '
          'Only extract the most material items explicitly supported by the document, up to two per array; empty arrays when absent. '
          'relationships: {subject,relation(supplies|customer_of|depends_on|constrained_by|competes_with|mitigates),object,quote}. '
          'bottlenecks: {company,type,severity(low|medium|high|unknown),duration,product,affected_revenue,mitigation,quote}. '
          'answers: {question_quote,answer_quote,question_topic,answer_topic,similarity,directness,specificity,skepticism,disagreement,core_answered,followup_needed,concern}. '
          'Answer scores are subjective 0..1 semantic judgments, never probabilities or price predictions. Use null when indeterminable. '
          'contradictions: {first_quote,second_quote,explanation}. Every quote must be an exact nonempty source substring. '
          'For an explicitly labeled prior/current document pair, optionally add comparisons: '
          '[{relation:confirms|updates|contradicts|new_claim,prior_quote,current_quote,explanation}]. '
          'Quotes must belong to their respective document. Only new_claim may have null prior_quote; '
          'new means absent from this compared source, not unprecedented in the world. '
          'Unknown contextual fields must be null; never infer unnamed suppliers or unreported revenue. Do not force disagreement from different periods or scopes. '
          'Stay concise to fit the output limit; research may be null. These source claims are unverified, not independently confirmed facts.')

def validate_quotes(output,text):
    if any(f.quote not in text for f in output.findings):raise ValueError('Unsupported quote')
    if output.research:
        for group in output.research.model_dump().values():
            for item in group:
                for key,value in item.items():
                    if key.endswith('quote') and value is not None and value not in text:raise ValueError('Unsupported semantic quote')

def project_analysis(db,result,document_id):
    if result.get('status') not in ('COMPLETE','CACHED'):return None
    p=result.get('analysis',{}).get('research')
    doc=db.get(document_id)
    if not p or not doc or doc['kind']!='document':return None
    research=SemanticResearch.model_validate(p);source=doc['payload'];symbol=source.get('symbol','')
    # Cache reuse does not produce a new observation or duplicate feature.
    rid=hashlib.sha256(('semantic-v1:'+document_id+':'+result['run_id']).encode()).hexdigest()
    available=max(datetime.fromisoformat(result['timestamp']),datetime.fromisoformat(source['received_at']))
    from backend.intelligence.documents import question_answer
    answers=[{**a.model_dump(),'lexical':question_answer(a.question_quote,a.answer_quote)} for a in research.answers]
    mean=lambda name:sum(v)/len(v) if (v:=[getattr(a,name) for a in research.answers if getattr(a,name) is not None]) else None
    direct=mean('directness')
    scores={'management_evasiveness':None if direct is None else 1-direct,'analyst_skepticism':mean('skepticism'),'management_analyst_disagreement':mean('disagreement')}
    payload={**research.model_dump(),'answers':answers,'scores':scores,'document_id':document_id,'period_end':source.get('period_end'),'provider':result['provider'],'model':result['model'],'prompt_version':result['prompt_version'],'source_reference':source['source_reference'],'available_at':available.isoformat(),'expires_at':(available+timedelta(days=90)).isoformat(),'warning':'Subjective semantic evidence with exact-source quotes; quotation validation does not establish factual truth or predictive validity.'}
    db.put('semantic_research',payload,symbol,record_id=rid,available_at=available.isoformat())
    if symbol:
        for name,value in scores.items():
            f=Feature(id=rid+':'+name,asset=AssetIdentifier(symbol=symbol,asset_class='crypto' if '-' in symbol else 'stock'),name=name,value=value,as_of=available,available_at=available,evidence_ids=[document_id,rid],provider=result['provider'],model=result['model'],expires_at=available+timedelta(days=90),quality={'calibrated':False,'prompt_version':result['prompt_version']})
            db.put('feature',f,symbol,available_at=available.isoformat())
    return payload
