import test from 'node:test';
import assert from 'node:assert/strict';
const base=process.env.TRADERX_FRONTEND_URL||'http://127.0.0.1:3000';
for(const path of ['/','/settings','/research','/experiments','/backtests','/models','/strategies','/risk','/providers','/crypto','/portfolio','/orders','/asset/BTC-USD','/earnings','/insiders','/institutions','/traders','/themes','/macro','/options','/scanner','/assets','/system','/coverage','/workers']){
 test('Next.js serves '+path,async()=>{const r=await fetch(base+path);assert.equal(r.status,200);const text=await r.text();assert.match(text,/TraderX/);assert.doesNotMatch(text,/sk-proj-/)});
}
test('Frontend proxy reaches backend safely',async()=>{const r=await fetch(base+'/api/v1/health');assert.equal(r.status,200);const d=await r.json();assert.equal(d.live_trading,false);assert.equal(d.execution,'internal_paper_only')});
test('Settings API exposes budgets without secrets',async()=>{const r=await fetch(base+'/api/v1/settings/ai');const d=await r.json();assert.equal(typeof d.usage.monthly_cost,'number');assert.ok(['off','local','openai','hybrid'].includes(d.current_provider));assert.equal(d.settings.api_key,undefined);assert.equal(d.settings.OPENAI_API_KEY,undefined)});
test('Browser origin isolation blocks untrusted mutation',async()=>{const r=await fetch(base+'/api/v1/risk/halt',{method:'POST',headers:{'Content-Type':'application/json','X-TraderX-Client':'local-ui','Origin':'https://untrusted.example'},body:JSON.stringify({halted:false})});assert.equal(r.status,403)});
test('App metadata has only TraderX branding',async()=>{const r=await fetch(base);const html=await r.text();const head=html.match(/<head>([\s\S]*?)<\/head>/)?.[1]||'';assert.match(head,/<title>TraderX/);assert.doesNotMatch(head,/name="(?:generator|author)"/);assert.match(head,/<meta name="application-name" content="TraderX"/);assert.equal(r.headers.get('x-powered-by'),null)});

test('Broker status never exposes credentials or enables live execution',async()=>{const r=await fetch(base+'/api/v1/execution/alpaca');assert.equal(r.status,200);const d=await r.json();assert.equal(d.live_trading,false);assert.equal(d.venue,'alpaca_paper');assert.equal(d.API_KEY,undefined);assert.equal(d.credentials,undefined)});
test('Risk reports covariance availability and bounded local sizing',async()=>{const r=await fetch(base+'/api/v1/risk');assert.equal(r.status,200);const d=await r.json();assert.equal(typeof d.analytics.covariance_available,'boolean');const size=await fetch(base+'/api/v1/risk/size',{method:'POST',headers:{'Content-Type':'application/json','X-TraderX-Client':'local-ui'},body:JSON.stringify({equity:100000,price:100,available_cash:100000})});assert.equal(size.status,200);const s=await size.json();assert.equal(s.status,'SIZING_ESTIMATE_ONLY');assert.equal(s.quantity,20)});

test('Experiment accounting reports all attempted trials',async()=>{const r=await fetch(base+'/api/v1/research/experiments/families');assert.equal(r.status,200);const d=await r.json();assert.equal(typeof d.registered_trials,'number');assert.equal(typeof d.failed_trials,'number');assert.equal(typeof d.families,'object')});
test('Execution capabilities distinguish read-only venues',async()=>{const r=await fetch(base+'/api/v1/execution/venues');assert.equal(r.status,200);const d=await r.json();assert.equal(d.live_trading,false);assert.equal(d.venues.length,4);assert.ok(!d.venues.some(v=>v.venue==='kalshi_demo'))});

test('Local retraining has explicit schedule and research-only scope',async()=>{const r=await fetch(base+'/api/v1/settings/training');assert.equal(r.status,200);const d=await r.json();assert.equal(typeof d.settings.enabled,'boolean');assert.ok(d.settings.interval_days>=1);assert.match(d.scope,/No language-model fine-tuning or automatic trading/)});

test('Historical coverage and cross-document evidence routes are available',async()=>{
 for(const kind of ['historical_dataset','document_comparison']){const r=await fetch(base+'/api/v1/records/'+kind);assert.equal(r.status,200);assert.ok(Array.isArray(await r.json()));}
});

test('Research studies expose benchmarks and protect reserved inputs',async()=>{
 const r=await fetch(base+'/api/v1/research/studies');assert.equal(r.status,200);const rows=await r.json();assert.ok(Array.isArray(rows));
 for(const row of rows){assert.equal(row.promotion_eligible,false);assert.equal(row.matrix,undefined);assert.ok(Array.isArray(row.features));assert.ok(row.trials.length<=54)}
 assert.equal((await fetch(base+'/api/v1/records/ml_study_input')).status,403);
});
test('Coverage distinguishes collected data from feature eligibility',async()=>{
 const r=await fetch(base+'/api/v1/system/research');assert.equal(r.status,200);const d=await r.json();assert.ok(Array.isArray(d.coverage));assert.ok(Array.isArray(d.macro_initial_series));
 const f=await fetch(base+'/api/v1/system/features/BTC-USD');assert.equal(f.status,200);
});
test('Eight main navigation destinations preserve specialist pages',async()=>{
 const html=await(await fetch(base)).text();const nav=html.match(/<nav aria-label="Primary navigation">([\s\S]*?)<\/nav>/)?.[1];assert.ok(nav);assert.equal((nav.match(/<a /g)||[]).length,8);
 for(const label of ['Overview','Scanner','Assets','Models','Research','Portfolio','System','Settings'])assert.ok(nav.includes(label));
});

test('Forward research is isolated and records quarantined evidence',async()=>{
 const r=await fetch(base+'/api/v1/research/forward');assert.equal(r.status,200);const d=await r.json();assert.ok(Array.isArray(d.studies));assert.ok(Array.isArray(d.decisions));assert.match(d.warning,/no external orders/i);
 for(const s of d.studies)assert.equal(s.evidence_policy,'quarantined_evaluation');
 assert.equal((await fetch(base+'/forward-studies')).status,200);
});
test('Universe coverage names price semantics and eligibility reasons',async()=>{
 const r=await fetch(base+'/api/v1/research/coverage');assert.equal(r.status,200);const d=await r.json();assert.ok(d.assets.length>=6);assert.equal(d.universe.policy,'retrospective_watchlist');
 for(const a of d.assets){assert.ok(Array.isArray(a.eligibility.reasons));for(const f of a.families){assert.ok(f.missingness>=0&&f.missingness<=1);assert.equal(typeof f.reason,'string')}}
 const cross=await(await fetch(base+'/api/v1/research/cross-sectional')).json();if(cross)assert.equal(cross.promotion_eligible,false);
});

test('Personal paper account remains separate and does not initialize on read',async()=>{
 const p=await(await fetch(base+'/api/v1/product/portfolio')).json();assert.ok(p.initial_cash>=100);assert.match(p.source,/Manual paper/);assert.ok(Array.isArray(p.orders));assert.ok(Array.isArray(p.positions));
 const model=await(await fetch(base+'/api/v1/research/forward')).json();assert.ok(model.studies.every(s=>s.id!==p.id));
});
test('Expanded universe is searchable and research forecasts are clearly qualified',async()=>{
 const r=await fetch(base+'/api/v1/product/universe');assert.equal(r.status,200);const rows=await r.json();assert.ok(rows.length>=100);assert.ok(rows.some(r=>r.symbol==='PLTR'));assert.ok(rows.some(r=>r.symbol==='BTC-USD'));
 for(const row of rows){assert.ok(Array.isArray(row.eligibility.reasons));if(row.model_prediction!=null)assert.match(row.forecast_status,/experimental/)}
});
test('Personal paper confirmation and origin checks cannot be bypassed',async()=>{
 const h={'Content-Type':'application/json','X-TraderX-Client':'local-ui'};
 let r=await fetch(base+'/api/v1/product/orders',{method:'POST',headers:h,body:JSON.stringify({preview_id:'nonexistent',confirmation:'yes'})});assert.equal(r.status,422);
 r=await fetch(base+'/api/v1/product/account/reset',{method:'POST',headers:h,body:JSON.stringify({starting_balance:10000,account_id:'nonexistent',confirmation:'yes'})});assert.equal(r.status,422);
 r=await fetch(base+'/api/v1/product/watchlist',{method:'PUT',headers:{...h,Origin:'https://untrusted.example'},body:JSON.stringify({symbol:'AAPL',saved:true})});assert.equal(r.status,403);
});
test('Watchlist and strategy comparison UI routes are served',async()=>{
 assert.equal((await fetch(base+'/watchlist')).status,200);const list=await(await fetch(base+'/api/v1/product/watchlist')).json();assert.ok(Array.isArray(list.symbols));
 const r=await fetch(base+'/api/v1/product/strategies');assert.equal(r.status,200);const data=await r.json();if(data){assert.equal(data.promotion_eligible,false);assert.ok(data.family_results.length>=20)}
});


test('Automatic model portfolio exposes isolated accounting and bounded risk',async()=>{
 const d=await(await fetch(base+'/api/v1/selection/portfolio')).json();assert.equal(d.isolation.external_execution,false);assert.equal(d.isolation.manual,true);assert.equal(d.isolation.scientific_forward,true);assert.ok(d.policy.maximum_position<=.2);assert.ok(d.account.initial_cash>=100);if(d.metrics.daily_return_observations<60)assert.equal(d.metrics.sharpe_like,null);
 assert.equal((await fetch(base+'/model-portfolio')).status,200);
});
test('Opportunity ranking and source registry expose evidence without forced promotion',async()=>{
 const d=await(await fetch(base+'/api/v1/selection/opportunities')).json();assert.ok(d.rows.length>=100);assert.ok(d.rows.every(r=>r.score>=0&&r.score<=100));
 const registry=await(await fetch(base+'/api/v1/selection/registry')).json();assert.ok(registry.count>=100);assert.ok(registry.rows.length<=100);for(const r of registry.rows)if(r.eligibility!=='eligible')assert.equal(r.meta_weight,0);
 const research=await(await fetch(base+'/api/v1/selection/policy-research')).json();assert.equal(research.results.length,14);assert.equal(research.promotion_eligible,false);
});
test('Automatic controls reject cross-origin mutation',async()=>{
 const r=await fetch(base+'/api/v1/selection/pause',{method:'POST',headers:{'Content-Type':'application/json','X-TraderX-Client':'local-ui',Origin:'https://untrusted.example'},body:JSON.stringify({paused:true})});assert.equal(r.status,403);
});

test('qualification diagnostics distinguish repeated decisions and unobserved gates',async()=>{
 const r=await fetch(base+'/api/v1/qualification/diagnostics');assert.equal(r.status,200);const d=await r.json();assert.equal(d.original.decisions,3514);assert.ok(d.original.unique_asset_feature_timestamps<3514);assert.equal(d.original.thresholds.length,5);assert.ok(d.original.thresholds.every(v=>v.orders_created===0));assert.equal((await fetch(base+'/decision-diagnostics')).status,200);
});
test('forward qualification exposes frozen states without authorizing external execution',async()=>{
 const d=await(await fetch(base+'/api/v1/qualification/evidence')).json();assert.equal(d.real_money_authorized,false);assert.ok(d.rows.length>0);for(const row of d.rows){assert.ok(row.criteria_hash);assert.ok(['RESEARCH_ONLY','FORWARD_TESTING','INSUFFICIENT_EVIDENCE','FAILED','QUALIFIED_FOR_MODEL_PAPER'].includes(row.state));assert.ok(row.remaining.forward_clusters>=0);assert.equal(row.real_money_authorized,false)}assert.equal((await fetch(base+'/forward-evidence')).status,200);
});
test('historical replay and research remain outside promotion evidence',async()=>{
 const d=await(await fetch(base+'/api/v1/qualification/replay')).json();assert.equal(d.scope,'historical_debug_only');assert.ok(d.trace_count>0);const r=await(await fetch(base+'/api/v1/qualification/research')).json();assert.equal(r.promotion_eligible,false);assert.equal(r.results.length,66);assert.equal(r.definition.version,'qualification-research-v2');
});
test('qualification replay rejects cross-origin mutation',async()=>{
 const r=await fetch(base+'/api/v1/qualification/replay',{method:'POST',headers:{'Content-Type':'application/json','X-TraderX-Client':'local-ui',Origin:'https://untrusted.example'},body:JSON.stringify({snapshots:1})});assert.equal(r.status,403);
});

test('Decision Cockpit preserves honest evidence and manual isolation',async()=>{
 const r=await fetch(base+'/api/v1/product/cockpit');assert.equal(r.status,200);const d=await r.json();assert.ok(d.rows.length>=100);assert.equal(d.external_execution,false);assert.equal(d.training_eligible,false);assert.ok(d.top.length<=10);
 for(const row of d.rows){assert.ok(['BUY','SELL','HOLD','NO TRADE','INSUFFICIENT EVIDENCE'].includes(row.view));assert.equal(row.families.length,11);assert.equal(new Set(row.families.map(f=>f.family)).size,11);if(!row.qualified)assert.equal(row.quality_label,'Experimental research signal');if(row.stale)assert.equal(row.view,'INSUFFICIENT EVIDENCE')}
});

test('Personal ideas reject untrusted edits and malformed target prices',async()=>{
 const before=await(await fetch(base+'/api/v1/product/cockpit')).json();const h={'Content-Type':'application/json','X-TraderX-Client':'local-ui'};
 let r=await fetch(base+'/api/v1/product/ideas',{method:'PUT',headers:{...h,Origin:'https://untrusted.example'},body:JSON.stringify({symbol:'PLTR',notes:'untrusted'})});assert.equal(r.status,403);
 r=await fetch(base+'/api/v1/product/ideas',{method:'PUT',headers:h,body:JSON.stringify({symbol:'PLTR',target_entry:-5})});assert.equal(r.status,422);
 const after=await(await fetch(base+'/api/v1/product/cockpit')).json();assert.deepEqual(after.ideas,before.ideas);assert.equal((await fetch(base+'/trade-ideas')).status,200);
});
test('Manual journal never becomes scientific evaluation or training',async()=>{
 const r=await fetch(base+'/api/v1/product/journal');assert.equal(r.status,200);const j=await r.json();assert.match(j.warning,/Never used as scientific evidence or training/);for(const t of j.trades){assert.equal(t.training_eligible,false);assert.equal(t.evaluation_eligible,false)}
});

for(const page of ['advanced-research','shadow-portfolio'])test('new ensemble page '+page,async()=>{assert.equal((await fetch(base+'/'+page)).status,200)});
test('ensemble shadow isolated and current research available',async()=>{const s=await(await fetch(base+'/api/v1/ensemble/shadow')).json();assert.equal(s.label,'EXPERIMENTAL — NOT VALIDATED');assert.equal(s.isolation.external_execution,false);assert.equal(s.isolation.training,true);const r=await(await fetch(base+'/api/v1/ensemble/research')).json();assert.ok(r.current.length>=100);for(const e of r.current){assert.ok(e.groups.every(g=>g.weight<=.50000001)||e.groups.length<2);if(e.action==='BUY')assert.ok(e.supporting.length>=2)}assert.ok(r.advanced.folds.length===3)});
test('manual automatic exits require valid explicit position consent',async()=>{assert.equal((await fetch(base+'/api/v1/ensemble/manual-exits',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol:'BTC-USD',account_id:'invalid',opened_at:'invalid',enabled:true})})).status,403);assert.equal((await fetch(base+'/api/v1/ensemble/manual-exits',{method:'PUT',headers:{'Content-Type':'application/json','X-TraderX-Client':'local-ui'},body:JSON.stringify({symbol:'BTC-USD',account_id:'invalid',opened_at:'invalid',enabled:true})})).status,422)});

test('Market structure research has explicit provider and execution boundaries',async()=>{
 const page=await fetch(base+'/market-structure');assert.equal(page.status,200);
 const r=await fetch(base+'/api/v1/structure/status');assert.equal(r.status,200);const d=await r.json();assert.equal(d.external_execution,false);assert.equal(d.futures,undefined);assert.ok(Array.isArray(d.intraday));assert.ok(Array.isArray(d.options));assert.ok(d.limits.max_requests_per_cycle<=100);assert.ok(d.limits.lookback_days<=31);
 for(const x of Object.values(d.microstructure))assert.match(x.scope,/FORWARD COLLECTED ONLY/);
});
test('Recommendation events and saved experiments preserve provenance',async()=>{
 const d=await(await fetch(base+'/api/v1/structure/status')).json();assert.ok(Array.isArray(d.recommendation_events));for(const e of d.recommendation_events){assert.ok(e.id);assert.ok(e.at);assert.ok(e.feature_snapshot);assert.ok(e.changes.length)}
 if(d.experiment){assert.ok(d.experiment.identity.code_version);assert.ok(d.experiment.identity.dataset_snapshot);assert.equal(d.experiment.genuine_oos_improvement,false);const id=encodeURIComponent(d.experiment.id);const c=await(await fetch(base+'/api/v1/structure/experiments/compare?a='+id+'&b='+id)).json();assert.deepEqual(c.changed,{})}
});

test('Alpha library page preserves research-only navigation',async()=>{const r=await fetch(base+'/alpha-library');assert.equal(r.status,200);const html=await r.text();assert.match(html,/Alpha library/)});
test('Alpha registry exposes frozen lifecycle and reserved forward benchmark',async()=>{const r=await fetch(base+'/api/v1/alpha/status');assert.equal(r.status,200);const d=await r.json();assert.equal(d.external_execution,false);assert.equal(d.distinct_families,12);assert.ok(d.policy.minimum_dates>=60);assert.ok(d.policy.prior_fraction>=.8);assert.ok(d.policy.maximum_weight_step<=.02);assert.equal(d.states.QUALIFIED_SIMULATION,0);assert.ok(d.alphas.every(a=>a.identity.universe.length>0&&a.policy_hash));assert.equal(d.research.genuine_oos_improvement,false);assert.equal(Object.keys(d.research.portfolio).length,7)});

test('Removed product pages and endpoints are unavailable',async()=>{for(const path of ['/social','/prediction-markets','/futures','/chat','/api/v1/auth/chatgpt/status','/api/v1/execution/kalshi'])assert.equal((await fetch(base+path)).status,404)});


test('Autonomous Research stays subordinate and exposes bounded, credential-free research status',async()=>{
 const page=await fetch(base+'/autonomous-research');assert.equal(page.status,200);
 const r=await fetch(base+'/api/v1/research/autonomous');assert.equal(r.status,200);const d=await r.json();
 assert.equal(d.budget.maximum_concurrent,1);assert.ok(d.budget.maximum_trials<=2);
 assert.ok(Array.isArray(d.experiments));assert.ok(Array.isArray(d.qualified_discoveries));
 assert.equal(d.credentials,undefined);assert.equal(d.API_KEY,undefined);assert.match(d.production,/no ensemble writes/);
 const denied=await fetch(base+'/api/v1/research/autonomous/register',{method:'POST',headers:{'Content-Type':'application/json','X-TraderX-Client':'local-ui'},body:JSON.stringify({code:'enable_live_trading()'})});assert.equal(denied.status,422);
});
