import test from 'node:test';
import assert from 'node:assert/strict';
const base=process.env.TRADERX_FRONTEND_URL||'http://127.0.0.1:3000';
for(const path of ['/','/settings','/research','/risk','/providers','/crypto','/portfolio','/asset/BTC-USD']){
 test('Next.js serves '+path,async()=>{const r=await fetch(base+path);assert.equal(r.status,200);const text=await r.text();assert.match(text,/TraderX/);assert.doesNotMatch(text,/sk-proj-/)});
}
test('Frontend proxy reaches backend safely',async()=>{const r=await fetch(base+'/api/v1/health');assert.equal(r.status,200);const d=await r.json();assert.equal(d.live_trading,false);assert.equal(d.execution,'internal_paper_only')});
test('Settings API exposes budgets without secrets',async()=>{const r=await fetch(base+'/api/v1/settings/ai');const d=await r.json();assert.equal(typeof d.usage.monthly_cost,'number');assert.ok(['off','local','openai','hybrid'].includes(d.current_provider));assert.equal(d.settings.api_key,undefined);assert.equal(d.settings.OPENAI_API_KEY,undefined)});
test('Browser origin isolation blocks untrusted mutation',async()=>{const r=await fetch(base+'/api/v1/risk/halt',{method:'POST',headers:{'Content-Type':'application/json','X-TraderX-Client':'local-ui','Origin':'https://untrusted.example'},body:JSON.stringify({halted:false})});assert.equal(r.status,403)});
test('App metadata has only TraderX branding',async()=>{const r=await fetch(base);const html=await r.text();const head=html.match(/<head>([\s\S]*?)<\/head>/)?.[1]||'';assert.match(head,/<title>TraderX/);assert.doesNotMatch(head,/name="(?:generator|author)"/);assert.doesNotMatch(head,/codex|chatgpt|openai/i);assert.equal(r.headers.get('x-powered-by'),null)});
