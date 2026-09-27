from datetime import datetime,timedelta,timezone
import numpy as np
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.storage.database import Database,Base,Job,LLMRun,Record
from backend.intelligence.documents import parse_form4,parse_13f,institution_changes
from backend.intelligence.ingest import store_document
from backend.intelligence.evidence_features import insider_snapshot,derive_document,refresh_evidence,emit_features
from backend.intelligence.transcripts import transcript_research
from backend.research.point_in_time import join_features_asof
from backend.schemas.contracts import now

@pytest.fixture
def db(tmp_path):
    db=Database('sqlite:///'+str(tmp_path/'evidence.db'));Base.metadata.create_all(db.engine);return db

def form4(owner='1',code='P',form='4',derivative=False,day=None,price='10'):
    tag='derivativeTransaction' if derivative else 'nonDerivativeTransaction'
    return f'''<ownershipDocument xmlns="urn:fixture"><documentType>{form}</documentType>
    <issuer><issuerCik>100</issuerCik><issuerTradingSymbol>TEST</issuerTradingSymbol></issuer>
    <reportingOwner><reportingOwnerId><rptOwnerCik>{owner}</rptOwnerCik><rptOwnerName>Fixture owner</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isOfficer>1</isOfficer><officerTitle>CFO</officerTitle></reportingOwnerRelationship></reportingOwner>
    <{tag}><securityTitle><value>Common</value></securityTitle><transactionDate><value>{day or now().date()}</value></transactionDate>
    <transactionCoding><transactionCode>{code}</transactionCode></transactionCoding>
    <transactionAmounts><transactionShares><value>20</value></transactionShares><transactionPricePerShare><value>{price}</value><footnoteId id="F1"/></transactionPricePerShare>
    <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode></transactionAmounts>
    <postTransactionAmounts><sharesOwnedFollowingTransaction><value>100</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
    </{tag}><footnotes><footnote id="F1">Private purchase under agreement.</footnote></footnotes></ownershipDocument>'''

def holding(shares=100,put='',value=1000):
    return f'<infoTable><nameOfIssuer>Fixture</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>123456789</cusip><value>{value}</value><shrsOrPrnAmt><sshPrnamt>{shares}</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt><putCall>{put}</putCall></infoTable>'

def save(db,text,kind='form4',**kwargs):
    return store_document(db,text=text,kind=kind,title='Fixture',source_reference='fixture://document',**kwargs)

def test_form4_roles_values_footnotes_and_nonfinite():
    p=parse_form4(form4())[0]
    assert p['kind']=='market_or_private_purchase' and p['previous_holdings']==80
    assert p['relative_to_previous']==.25 and p['owners'][0]['officer']
    assert p['footnotes']==['Private purchase under agreement.']
    assert parse_form4(form4(price=''))[0]['value'] is None
    for invalid in ('NaN','inf','-1'):
        with pytest.raises(ValueError):parse_form4(form4(price=invalid))

def test_cluster_dedup_and_amendment_invalidation(db):
    save(db,form4())
    store_document(db,text=form4(),kind='form4',title='Same transaction',source_reference='fixture://duplicate')
    save(db,form4(owner='2'));save(db,form4(owner='3',code='A'));save(db,form4(owner='4',derivative=True))
    snapshot=insider_snapshot(db,'TEST')
    assert snapshot['windows']['7']['purchase_count']==2
    assert snapshot['windows']['7']['known_buyers']==2 and snapshot['windows']['7']['cluster']
    assert len(snapshot['evidence_ids'])==5
    save(db,form4(form='4/A'))
    snapshot=insider_snapshot(db,'TEST')
    assert snapshot['status']=='AMENDMENT_REVIEW_REQUIRED'
    assert all(v is None for v in snapshot['metrics'].values())
    features=db.records('feature','TEST')
    joined=join_features_asof([now()],features)
    assert np.isnan(joined['insider_purchase_count_7d'][0])

def test_13f_units_entity_period_and_instrument_identity(db):
    a=save(db,'<informationTable>'+holding()+holding(10,'Put')+'</informationTable>','13f',entity_id='fund1',period_end='2025-03-31',value_unit='thousands')
    save(db,holding(9999),'13f',entity_id='fund2',period_end='2025-06-30')
    b=save(db,holding(200),'13f',entity_id='fund1',period_end='2025-06-30',value_unit='dollars')
    result=b['research']
    assert result['previous_document_id']==a['id'] and result['reported_value_usd']==1000
    changes={r['put_call']:r for r in result['changes']}
    assert changes['']['shares_change']==100 and changes['Put']['status']=='closed'
    with pytest.raises(ValueError):parse_13f('<informationTable/>')
    with pytest.raises(ValueError):parse_13f(holding(value='nan'))
    merged=institution_changes(parse_13f('<informationTable>'+holding(10)+holding(20)+'</informationTable>'),parse_13f(holding(35)))
    assert merged[0]['shares_change']==5

def test_transcript_explicit_roles_and_changes(db):
    first='Jane (CEO): We expect revenue of 100.\nOperator: Question-and-answer session.\nAlex (Analyst): What is the capacity target?\nJane (CEO): Our capacity target is 20. Supply constraints delay production.'
    a=save(db,first,'transcript',symbol='TEST',period_end='2025-03-31')
    b=save(db,first.replace('100','150'),'transcript',symbol='TEST',period_end='2025-06-30')
    research=b['research']
    assert research['previous_document_id']==a['id']
    assert len(research['qa_pairs'])==1 and research['bottlenecks']
    assert research['semantic_evasiveness'] is None and research['changes']
    unknown=transcript_research('Jane: Results were good.\nAlex: How much?')
    assert unknown['unknown_speaker_turns']==2 and unknown['qa_pairs']==[]
    assert unknown['metrics']['qa_numeric_specificity'] is None

def test_missing_company_does_not_compare_unrelated_transcripts(db):
    save(db,'We expect 100.','transcript',period_end='2025-03-31')
    result=save(db,'We expect 900.','transcript',period_end='2025-06-30')
    assert result['research']['previous_document_id'] is None

def test_future_publication_defers_features_and_jobs(db):
    future=now()+timedelta(days=1)
    result=save(db,'We expect 100.','transcript',symbol='TEST',published_at=future)
    assert result['research']['status']=='NOT_YET_PUBLISHED'
    assert db.records('feature')==[]
    with Session(db.engine) as s:
        assert s.get(Job,result['id']).due_at==future.isoformat()
        assert list(s.scalars(select(LLMRun)))==[]
    assert refresh_evidence(db)['documents_checked']==0

def test_expiry_and_null_invalidation_do_not_leak(db):
    t=datetime(2025,1,1,tzinfo=timezone.utc)
    emit_features(db,'TEST',{'value':3},['a'],t,expires_at=t+timedelta(days=1))
    emit_features(db,'TEST',{'value':7},['b'],t+timedelta(days=2))
    emit_features(db,'TEST',{'value':None},['c'],t+timedelta(days=3))
    result=join_features_asof([t-timedelta(seconds=1),t,t+timedelta(days=1),t+timedelta(days=2),t+timedelta(days=3)],db.records('feature'))
    assert np.isnan(result.value[0]) and result.value[1]==3
    assert np.isnan(result.value[2]) and result.value[3]==7 and np.isnan(result.value[4])

def test_derivation_idempotent_recoverable_and_rolling(db):
    result=save(db,form4());count=len(db.records('feature'))
    assert save(db,form4())['status']=='ALREADY_STORED'
    assert len(db.records('feature'))==count
    with db.transaction() as s:
        for r in s.scalars(select(Record).where(Record.kind=='insider_research')):s.delete(r)
    assert refresh_evidence(db)['status']=='WORKING'
    count=len(db.records('insider_research'))
    refresh_evidence(db)
    assert len(db.records('insider_research'))==count

def test_metadata_changes_are_distinct_without_losing_source(db):
    a=save(db,holding(),'13f',entity_id='fund',period_end='2025-03-31')
    b=save(db,holding(),'13f',entity_id='fund',period_end='2025-03-31',value_unit='thousands')
    assert a['id']!=b['id'] and b['research']['reported_value_usd']==1000000
    assert db.get(b['id']+'event')['payload']['payload']['document_id']==b['id']

def test_empty_amendment_still_blocks_unreconciled_features(db):
    save(db,form4())
    save(db,'<ownershipDocument><documentType>4/A</documentType><issuer><issuerTradingSymbol>TEST</issuerTradingSymbol></issuer></ownershipDocument>',symbol='TEST')
    assert insider_snapshot(db,'TEST')['status']=='AMENDMENT_REVIEW_REQUIRED'

def test_duplicate_allocations_are_one_concentration_position(db):
    r=save(db,'<informationTable>'+holding(10,value=100)+holding(20,value=200)+'</informationTable>','13f')['research']
    assert r['source_line_count']==2 and r['position_count']==1 and r['concentration_hhi']==1

def test_bad_legacy_document_does_not_block_other_symbols(db):
    db.put('document',{'kind':'form4','text':'bad XML','symbol':'BAD'},'BAD')
    save(db,form4())
    result=refresh_evidence(db)
    assert result['status']=='DEGRADED'
    assert len(db.records('insider_research','TEST'))>=2

def test_consensus_compares_same_period_and_distinct_managers(db):
    from backend.intelligence.evidence_features import institutional_consensus
    save(db,holding(50),'13f',entity_id='a',period_end='2025-03-31')
    save(db,holding(100),'13f',entity_id='a',period_end='2025-06-30')
    save(db,holding(200),'13f',entity_id='b',period_end='2025-06-30')
    save(db,holding(500),'13f',entity_id='stale',period_end='2025-03-31')
    save(db,holding(999),'13f',period_end='2025-06-30')
    r=institutional_consensus(db)
    assert r['manager_count']==2 and r['excluded_unidentified_documents']==1
    assert r['holdings'][0]['manager_count']==2 and r['holdings'][0]['managers_adding']==1
    assert r['managers_with_prior_period']==1 and len(r['evidence_ids'])==3

def test_api_rejects_bad_xml_without_partial_records_and_future_ai(db):
    from fastapi.testclient import TestClient
    from backend.api.main import create_app
    with TestClient(create_app(db,start_workers=False)) as c:
        h={'X-TraderX-Client':'local-ui'}
        response=c.post('/api/v1/documents',json={'kind':'form4','text':'<bad','title':'Fixture','source_reference':'fixture'},headers=h)
        assert response.status_code==422 and db.records('document')==[] and db.records('raw')==[]
        response=c.post('/api/v1/documents',json={'kind':'transcript','text':'We expect 20.','title':'Fixture','source_reference':'fixture','published_at':(now()+timedelta(days=1)).isoformat()},headers=h)
        rid=response.json()['id']
        assert c.post('/api/v1/documents/'+rid+'/analyze',headers=h).status_code==409
