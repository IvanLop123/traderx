"""Human-readable data availability, separate from predictor eligibility."""
from backend.research.features import build_frame,select_features,SOURCES

def feature_coverage(db,symbol):
    df,x,groups,notes=build_frame(db,symbol)
    end=int(len(df)*.6)
    names,medians,excluded=select_features(x,groups,list(range(60,end)),list(SOURCES))
    return {'symbol':symbol,'available_columns':len(x.columns),'eligible_columns':len(names),
            'families':[{ 'family':f,'source':source,'available':sum(groups[n]==f for n in x),
                         'eligible':sum(groups[n]==f for n in names),'reason':notes.get(f,'Training-only coverage and redundancy filters apply')}
                        for f,source in SOURCES.items()], 'included':names,'excluded':excluded}

def universe_coverage(db):
    import pandas as pd
    from backend.research.universe import load_universe,eligible_at
    from backend.research.history import HistoryStore
    from backend.schemas.contracts import now
    universe=load_universe(db)
    if len(universe.instruments)>50:return wide_universe_coverage(db)
    store=HistoryStore(db);assets=[];families={}
    from backend.research.features import stable_hash
    signature=stable_hash(universe.model_dump(mode='json'))
    cached=db.setting('universe_coverage_cache',{})
    if cached.get('signature')==signature and pd.Timestamp(cached['result']['updated_at'])>pd.Timestamp(now())-pd.Timedelta(minutes=5):return cached['result']
    calendar=db.setting('research_calendar',{}).get('sessions',[])
    for instrument in universe.instruments:
        symbol=instrument.symbol;manifest=store.manifest(symbol);raw=store.read(symbol,'raw')
        expected=[s['date'] for s in calendar] if instrument.asset_class!='crypto' else list(pd.date_range(raw[0]['timestamp'],raw[-1]['timestamp'],freq='D')) if raw else []
        eligibility=eligible_at(instrument,raw,now(),universe.filters_for(instrument),expected_sessions=expected,strict_membership=universe.policy=='archived_membership')
        entry={'symbol':symbol,'asset_class':instrument.asset_class,'history':manifest,'eligibility':eligibility,'families':[]}
        try:
            df,x,groups,notes=build_frame(db,symbol);n=len(df);train_end=int(n*.6);fit=list(range(60,train_end))
            names,_,excluded=select_features(x,groups,fit,list(SOURCES)) if len(fit)>=64 else ([],{}, {})
            for family,source in SOURCES.items():
                cols=[c for c in x if groups[c]==family];valid=x[cols].notna().any(axis=1) if cols else pd.Series(False,index=x.index);count=int(valid.sum());selected=[c for c in names if groups[c]==family]
                reason='Training-window filters passed; ablation still required' if selected else notes.get(family) if not cols else '; '.join(sorted({excluded.get(c,'Insufficient training history') for c in cols}))
                dates=df.loc[valid,'available_at'];pit='public-time reconstruction; retrospective provider vintage' if family in ('price','technical','regime','cross_asset','macro','sec','crypto_structure') and count else 'unverified / not mapped'
                item={'family':family,'provider':source,'earliest':str(dates.iloc[0]) if count else None,'latest':str(dates.iloc[-1]) if count else None,'observations':count,'missingness':1-count/n if n else 1,'point_in_time_policy':pit,'eligible':bool(selected),'eligible_columns':selected,'reason':reason,'raw_rows':n,'minimum_training_rows':64,'minimum_training_coverage':.8}
                entry['families'].append(item);agg=families.setdefault(family,{'family':family,'provider':source,'assets':[],'eligible_assets':[],'observations':0})
                if count:agg['assets'].append(symbol);agg['observations']+=count
                if selected:agg['eligible_assets'].append(symbol)
        except ValueError:entry['error']='Insufficient valid daily history'
        assets.append(entry)
    result={'universe':universe.model_dump(mode='json'),'assets':assets,'families':list(families.values()),'backfill':db.setting('historical_backfill_status',{}),'extensions':{k:v for k,v in db.setting('extended_history_status',{}).items() if k!='sip'},'limitations':['Current watchlist is retrospective; inactive metadata is preserved but does not establish historical membership.','Provider-adjusted stock bars are research values, never executable prices.','Observation counts across correlated assets are not independent sample counts.'],'updated_at':now().isoformat()}

    db.set_setting('universe_coverage_cache',{'signature':signature,'result':result})
    return result

def wide_universe_coverage(db,prepared=None):
    """One shared panel profile for hundreds of assets; no repeated six-peer joins."""
    import pandas as pd
    from backend.research.strategies import make_panel,FAMILIES
    from backend.product.market import ProductMarket
    from backend.research.universe import load_universe
    from backend.research.history import HistoryStore
    from backend.research.features import stable_hash
    from backend.schemas.contracts import now
    u=load_universe(db);signature=stable_hash(u.model_dump(mode='json'));cached=db.setting('universe_coverage_cache',{})
    if cached.get('signature')==signature and cached.get('profile')=='expanded_strategy_panel':return cached['result']
    panel,_=prepared or make_panel(db);market=ProductMarket(db);summaries={r['symbol']:r for r in market.universe()};store=HistoryStore(db);assets=[];aggregates={};groups={}
    for name,frame in panel.groupby('symbol'):groups[name]=frame
    columns={'price':['return_1','return_5','return_20'],'technical':['rsi','bollinger_z','volume_zscore','breakout_20','bollinger_width','vol_of_vol'],'regime':['regime_trend','regime_vol_ratio'],'cross_asset':['relative_momentum','relative_volatility','momentum_rank','volatility_rank','pair_zscore'],'macro':['macro_FEDFUNDS','macro_UNRATE','macro_T10Y2Y'],'sec':FAMILIES['insider_event'],'crypto_structure':['funding_paid','funding_premium'],'text':[],'energy':[]}
    for i in u.instruments:
        frame=groups.get(i.symbol,pd.DataFrame());n=len(frame);fit=frame.iloc[60:int(n*.6)];entry={'symbol':i.symbol,'asset_class':i.asset_class,'history':store.manifest(i.symbol),'eligibility':summaries[i.symbol]['eligibility'],'families':[]}
        for family,source in SOURCES.items():
            cols=[c for c in columns.get(family,[]) if c in frame];valid=frame[cols].notna().any(axis=1) if cols else pd.Series(False,index=frame.index);count=int(valid.sum());selected=[c for c in cols if len(fit)>=64 and fit[c].notna().mean()>=.8 and fit[c].nunique()>1];dates=frame.loc[valid,'date'] if count else []
            item={'family':family,'provider':source,'earliest':str(dates.iloc[0]) if count else None,'latest':str(dates.iloc[-1]) if count else None,'observations':count,'missingness':1-count/n if n else 1,'point_in_time_policy':'Timestamped public reconstruction; retrospective historical price vintage' if count else 'unavailable / unmapped','eligible':bool(selected),'eligible_columns':selected,'reason':'Representative first-60% coverage screen; actual family folds and ablations decide usefulness' if selected else 'Not enough verified nonconstant early training coverage; never forced into a model','raw_rows':n,'minimum_training_rows':64,'minimum_training_coverage':.8}
            entry['families'].append(item);agg=aggregates.setdefault(family,{'family':family,'provider':source,'assets':[],'eligible_assets':[],'observations':0})
            if count:agg['assets'].append(i.symbol);agg['observations']+=count
            if selected:agg['eligible_assets'].append(i.symbol)
        assets.append(entry)
    result={'universe':u.model_dump(mode='json'),'assets':assets,'families':list(aggregates.values()),'backfill':db.setting('historical_backfill_status',{}),'extensions':{'expanded':db.setting('product_expansion',{}).get('universe')},'limitations':['Expanded-strategy panel profile; three macro series and separate families. Legacy six-asset models retain their own richer feature profiles.','Retrospective membership; current capitalization and historical delisting returns are not verified.','Adjusted history is never an executable price. Cross-asset rows are correlated.'],'updated_at':now().isoformat()}
    db.set_setting('universe_coverage_cache',{'signature':signature,'profile':'expanded_strategy_panel','result':result});return result
