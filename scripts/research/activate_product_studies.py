"""Enroll bounded independent research books, without promoting or placing orders."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from backend.storage.database import Database
from backend.research.strategies import make_panel,publish_current_forecasts
from backend.research.forward import ForwardStudies,EnrollRequest,ForwardPolicy
from backend.research.coverage import wide_universe_coverage
from backend.product.market import ProductMarket

def refresh(db):
 prepared=make_panel(db);forecast=publish_current_forecasts(db,prepared);wide_universe_coverage(db,prepared);return forecast
if __name__=='__main__':
 db=Database();print('Preparing shared current research panel',flush=True);forecast=refresh(db);print('Forecasts '+str(forecast['count']),flush=True)
 study=db.get(db.setting('strategy_latest')['id'])['payload'];service=ForwardStudies(db);universe={r['symbol']:r for r in ProductMarket(db).universe()}
 # Fixed, declared examples span established, niche, ETF and crypto exposures. No holdout selection.
 pools={'stock':['PLTR','JPM','FIX','STRL','HIMS','CALM'],'etf':['SPY','IWM','XBI','URA'],'crypto':['BTC-USD','ETH-USD','SOL-USD']};enrolled=[]
 for r in study['family_results']:
  if r['status']!='RESEARCH_ONLY' or r['family']=='pairs_relative_value':continue
  for symbol in pools[r['asset_class']][:2]:
   if universe.get(symbol,{}).get('eligibility',{}).get('eligible'):
    s=service.enroll(EnrollRequest(model_id=r['model_id'],symbol=symbol,policy=ForwardPolicy(initial_cash=10000)));enrolled.append(s['id'])
 # Additional niche and thematic assets use the momentum family, without performance selection.
 for cls,symbols in pools.items():
  model=next((r for r in study['family_results'] if r['asset_class']==cls and r['family']=='momentum' and r['status']=='RESEARCH_ONLY'),None)
  if model:
   for symbol in symbols[2:]:
    if universe.get(symbol,{}).get('eligibility',{}).get('eligible'):enrolled.append(service.enroll(EnrollRequest(model_id=model['model_id'],symbol=symbol,policy=ForwardPolicy(initial_cash=10000)))['id'])
 result={'forecasts':forecast,'new_cohorts':len(set(enrolled)),'all_cohorts':len(service.studies()),'ids':sorted(set(enrolled))};Path('data/product_phase/activation.json').write_text(json.dumps(result,indent=2));print('Cohorts '+str(result['all_cohorts']),flush=True)
