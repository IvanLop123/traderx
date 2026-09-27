"""Deterministic document parsing and evidence-backed thematic relationships."""
import re
import math
from collections import Counter
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException
from xml.etree.ElementTree import ParseError

THEMES={'nuclear':['uranium','reactor','nuclear','haleu','enrichment'], 'robotics':['robot','actuator','automation','machine vision'],
        'ai_infrastructure':['gpu','data center','semiconductor','networking','cooling'], 'power':['grid','electricity','power capacity','transformer']}
BOTTLENECKS=['capacity','supply','labor','regulatory','grid','financing','inventory','logistics','fuel']

def narrative_features(text):
    sentences=re.split(r'(?<=[.!?])\s+|\n+',text)
    hedges=re.findall(r'\b(may|might|perhaps|uncertain|expect|approximately)\b',text,re.I)
    numbers=re.findall(r'\b\d+(?:\.\d+)?%?\b',text)
    words=re.findall(r'\w+',text)
    themes={theme:[s for s in sentences if any(re.search(r'\b'+re.escape(term),s,re.I) for term in terms)] for theme,terms in THEMES.items()}
    bottlenecks=[{'type':term,'quote':s,'confidence':None,'method':'keyword_match'} for s in sentences for term in BOTTLENECKS
                 if re.search(r'\b'+term+r'\b',s,re.I) and re.search(r'constraint|shortage|delay|limit|bottleneck',s,re.I)]
    return {'word_count':len(words),'numeric_mentions':len(numbers),'hedge_fraction':len(hedges)/max(1,len(words)),
            'themes':{k:v for k,v in themes.items() if v},'bottlenecks':bottlenecks,'method':'lexical-v1','warning':'Keyword evidence requires contextual review; no inferred direction.'}

def question_answer(question,answer):
    q=set(re.findall(r'\b\w{4,}\b',question.lower())); a=set(re.findall(r'\b\w{4,}\b',answer.lower()))
    return {'lexical_overlap':len(q&a)/max(1,len(q|a)),'answer_words':len(answer.split()),
            'numerical_specificity':len(re.findall(r'\d+(?:\.\d+)?',answer))/max(1,len(answer.split())),
            'hedging':narrative_features(answer)['hedge_fraction'],'semantic_directness':None,
            'warning':'Lexical proxy; semantic evasiveness requires text analysis and validation.'}

def safe_xml_root(xml):
    try:return ET.fromstring(xml)
    except (ParseError,DefusedXmlException):raise ValueError('Invalid or unsafe XML document') from None

def ownership_root(xml):
    root=safe_xml_root(xml)
    for e in root.iter():e.tag=e.tag.split('}')[-1]
    if root.tag!='ownershipDocument':raise ValueError('Expected SEC ownership-document XML')
    return root

def parse_form4(xml):
    root=ownership_root(xml)
    def value(node,path,default=''): return node.findtext(path,default) if node is not None else default
    def numeric(node,path):
        raw=value(node,path)
        if not raw.strip():return None
        result=float(raw.replace(',',''))
        if not math.isfinite(result) or result<0:raise ValueError('Filing numeric values must be finite and nonnegative')
        return result
    owners=[{'cik':value(o,'.//rptOwnerCik'),'name':value(o,'.//rptOwnerName'),'title':value(o,'.//officerTitle'),
             'director':value(o,'.//isDirector') in ('1','true'),'officer':value(o,'.//isOfficer') in ('1','true'),
             'ten_percent_owner':value(o,'.//isTenPercentOwner') in ('1','true')} for o in root.findall('.//reportingOwner')]
    footnotes={f.attrib.get('id'):''.join(f.itertext()) for f in root.findall('.//footnote')}
    title=owners[0]['title'] if owners else ''
    results=[]
    for t in root.findall('.//nonDerivativeTransaction')+root.findall('.//derivativeTransaction'):
        code=value(t,'.//transactionCode'); shares=numeric(t,'.//transactionShares/value')
        price=numeric(t,'.//transactionPricePerShare/value');after=numeric(t,'.//sharesOwnedFollowingTransaction/value')
        acquired=value(t,'.//transactionAcquiredDisposedCode/value')
        prior=(after-shares if acquired=='A' else after+shares) if acquired in ('A','D') and after is not None and shares is not None else None
        results.append({'code':code,'kind':{'P':'market_or_private_purchase','S':'market_or_private_sale','A':'grant_or_award','M':'exercise_or_conversion','F':'withholding','C':'conversion'}.get(code,'other'),
            'shares':shares,'price':price,'value':shares*price if price is not None and shares is not None else None,'previous_holdings':prior if prior is None or prior>=0 else None,
            'relative_to_previous':shares/prior if prior is not None and prior>0 and shares is not None else None,'date':value(t,'.//transactionDate/value'),
            'officer_title':title,'owners':owners,'issuer_cik':value(root,'.//issuerCik'),'issuer_symbol':value(root,'.//issuerTradingSymbol'),
            'security':value(t,'.//securityTitle/value'),'derivative':t.tag=='derivativeTransaction','acquired_disposed':value(t,'.//transactionAcquiredDisposedCode/value'),
            'ownership':value(t,'.//directOrIndirectOwnership/value'),'planned_10b5_1':value(root,'.//aff10b5One') in ('1','true'),
            'form':value(root,'documentType','4'),'original_submission_date':value(root,'dateOfOriginalSubmission'),
            'footnotes':[footnotes[f.attrib.get('id')] for f in t.findall('.//footnoteId') if f.attrib.get('id') in footnotes],
            'personal_capital_candidate':code=='P' and t.tag!='derivativeTransaction',
            'caveat':'P/S includes market or private transactions. Footnotes and ownership require review; personal cash and execution venue are not proven.'})
    return results

def parse_13f(xml):
    root=safe_xml_root(xml)
    for e in root.iter(): e.tag=e.tag.split('}')[-1]
    def numeric(node,path,required=True):
        raw=node.findtext(path)
        if raw is None or not raw.strip():
            if required:raise ValueError('13F holding is missing '+path)
            return None
        result=float(raw.replace(',',''))
        if not math.isfinite(result) or result<0:raise ValueError('13F numeric values must be finite and nonnegative')
        return result
    nodes=[root] if root.tag=='infoTable' else root.findall('.//infoTable')
    if not nodes:raise ValueError('No 13F information-table holdings found; import the information-table XML')
    if any(not n.findtext('cusip') for n in nodes):raise ValueError('13F holding requires a CUSIP')
    return [{'issuer':n.findtext('nameOfIssuer'),'cusip':n.findtext('cusip'),'reported_value':numeric(n,'value'),
             'shares':numeric(n,'shrsOrPrnAmt/sshPrnamt'),'put_call':n.findtext('putCall'),'class':n.findtext('titleOfClass'),
             'share_type':n.findtext('shrsOrPrnAmt/sshPrnamtType'),'figi':n.findtext('figi'),'discretion':n.findtext('investmentDiscretion'),
             'voting_sole':numeric(n,'votingAuthority/Sole',False),'value_units':'as_reported_unspecified'} for n in nodes]

def institution_changes(previous,current):
    def aggregate(rows):
        result={}
        for p in rows:
            key=(p['cusip'],p.get('put_call') or '',p.get('class') or '',p.get('share_type') or 'SH')
            if key not in result:result[key]={**p,'shares':0,'reported_value':0}
            result[key]['shares']+=p['shares'];result[key]['reported_value']+=p['reported_value']
        return result
    old=aggregate(previous);new=aggregate(current)
    return [{'cusip':key[0],'put_call':key[1],'class':key[2],'share_type':key[3],'shares_change':new.get(key,{}).get('shares',0)-old.get(key,{}).get('shares',0),
             'status':'new' if key not in old else 'closed' if key not in new else 'changed',
             'warning':'Holdings as of quarter end; usable only after actual filing publication.'} for key in sorted(old.keys()|new.keys())]

def theme_graph(text,source_id,company):
    parsed=narrative_features(text); edges=[]
    for theme,quotes in parsed['themes'].items():
        edges.append({'from':company,'to':theme,'relationship':'mentions','evidence_id':source_id,'quote':quotes[0]})
    return {'nodes':list({company,*parsed['themes'].keys()}),'edges':edges}
