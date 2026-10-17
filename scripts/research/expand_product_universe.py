"""Explicit bounded expansion; real provider identity and history, no execution."""
import sys,asyncio,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from backend.storage.database import Database
from backend.providers.market import MarketProviders,ProviderError
from backend.providers.history import HistoricalBackfill
from backend.research.universe import Universe,load_universe
from backend.research.history import HistoryStore
from backend.schemas.contracts import now
STOCKS='''AAPL MSFT NVDA AMZN GOOG GOOGL META TSLA AVGO ORCL CRM ADBE AMD INTC QCOM TXN MU AMAT LRCX KLAC ADI MRVL NXPI ON MPWR MCHP WDC STX DELL HPQ HPE IBM CSCO ANET PANW CRWD FTNT ZS NET DDOG SNOW MDB NOW TEAM HUBS WDAY INTU ADSK CDNS SNPS UBER ABNB BKNG DASH PLTR APP SHOP TTD ROKU PINS SNAP RBLX EA TTWO JPM BAC WFC C GS MS SCHW BLK BX KKR APO AXP V MA PYPL COF USB PNC TFC FITB KEY RF CFG HBAN ALL TRV PGR CB AFL MET PRU AIG JNJ LLY ABBV MRK PFE BMY AMGN GILD REGN VRTX BIIB MRNA UNH HUM CVS CI ELV HCA ISRG MDT SYK BSX ABT TMO DHR IQV DXCM PODD ALGN EW XOM CVX COP EOG OXY SLB HAL BKR DVN FANG VLO MPC PSX LNG KMI WMB OKE TPL CTRA NEE DUK SO AEP EXC XEL SRE D CEG VST NRG AES WMT COST TGT HD LOW TJX ROST DG DLTR AMZN EBAY ETSY WSM RH CROX DECK ONON BROS CAVA CMG MCD SBUX YUM DPZ KO PEP PG CL KMB GIS KHC MDLZ HSY STZ CELH MNST PM MO BTI NKE LULU CAT DE GE HON RTX LMT NOC GD BA LHX HWM TDG HEI ETN PH ROK EMR ITW DOV IR FAST GWW PCAR CMI PWR VRT TT CARR JCI OTIS UNP CSX NSC UPS FDX UAL DAL LUV AAL ALK ODFL SAIA XPO JBHT WM RSG URI NUE STLD CLF AA FCX SCCO NEM GOLD AEM WPM FNV DOW DD LYB APD LIN ECL SHW PPG MLM VMC EXP AMT PLD EQIX DLR O SPG PSA WELL VTR AVB EQR ARE CCI SBAC WY NFLX DIS CMCSA CHTR T VZ TMUS WBD FOXA PARA SPOT SONY DUOL BILL SOFI AFRM UPST HOOD COIN MSTR MARA RIOT CLSK HUT IREN RKLB ASTS LUNR RDW PL ENPH SEDG FSLR RUN NXT BE FLNC STEM CHPT QS ALB LAC MP LEU CCJ UEC DNN SMR OKLO BWXT KGS LBRT PR DO AR ANTERO RXRX IOVA CRSP NTLA EDIT BEAM HIMS DOCS GH NTRA EXAS TWST PACB RGEN ACLS COHR LITE MTSI INDI AEHR CAMT ICHR NVMI FORM SITM MOD ENS HAYW LNN WTS FIX IESC STRL TNET ASGN KFY RHI BOOT CALM INDB BANF CVBF FULT WAL ZION CMA NYCB OZK SF STIF'''.split()
ETFS='''SPY QQQ IWM MDY IJR VTI VOO IVV RSP VTV VUG VB VO IWB IWD IWF SCHB SCHD VYM DVY QUAL MTUM USMV SPLV VLUE SIZE XLF XLV XLE XLI XLU XLK XLY XLP XLB XLRE XLC VGT VHT VFH VIS VDC VCR VDE VAQ XBI IBB SMH SOXX IGV SKYY CLOU CIBR HACK ARKK ARKG ARKW KWEB TAN ICLN QCLN PBW LIT REMX COPX URA URNM PAVE ITA XAR JETS KRE KBE IYR VNQ IYT XRT XHB ITB GDX GDXJ SLV GLD IAU SLX XME XOP OIH AMLP TLT IEF SHY TIP HYG LQD BND AGG EMB EEM VWO EFA VEA EWJ EWZ EWY INDA FM BOTZ ROBO AIQ FINX HERO ESPO BUG FFTY IPO PRNT WOOD DBA DBB DBC USO UNG WEAT CORN SOYB'''.split()
async def main():
 db=Database();p=MarketProviders(db);h=HistoricalBackfill(p);root=Path('data/product_phase');root.mkdir(exist_ok=True)
 await h.instruments();snap=next(r['payload'] for r in db.records('instrument_snapshot') if r['payload']['status']=='active');listing={r['symbol']:r for r in snap['instruments']}
 old=load_universe(db).model_dump(mode='json');existing={i['symbol']:i for i in old['instruments']};rejected=[]
 for s in dict.fromkeys(STOCKS+ETFS):
  item=listing.get(s)
  if not item or not item.get('tradable'):rejected.append(s);continue
  existing[s]={**existing.get(s,{}),'symbol':s,'asset_class':'etf' if s in ETFS else 'stock','instrument_id':item['id'],'exchange':item.get('exchange'),'name':item.get('name',s),'active':True}
 old.update(name='Expanded diversified US research universe',instruments=list(existing.values()),maximum_training_assets=500,backfill_batch_size=25)
 u=Universe.model_validate(old);db.set_setting('research_universe',u.model_dump(mode='json'));Path('config/research_universe.json').write_text(json.dumps(u.model_dump(mode='json'),indent=2)+'\n')
 path=root/'expansion.json';results=json.loads(path.read_text()) if path.exists() else {};results['universe']={'count':len(existing),'not_active_or_not_tradable':rejected,'retrospective':True};path.write_text(json.dumps(results,indent=2));print('Configured '+str(len(existing))+' instruments',flush=True)
 stocks=[i.symbol for i in u.instruments if i.asset_class in ('stock','etf')];store=HistoryStore(db)
 for start in range(0,len(stocks),25):
  batch=stocks[start:start+25];key='batch_'+str(start)
  if results.get(key,{}).get('status')=='COMPLETE':continue
  try:
   values=await h.alpaca(batch,feed='sip');results[key]={'status':'COMPLETE','series':[{'symbol':r['symbol'],'count':r['count'],'start':r['start'],'end':r['end'],'adjustment':r['adjustment']} for r in values]}
   await h.corporate_actions(batch)
  except Exception as e:results[key]={'status':getattr(e,'status',type(e).__name__)}
  path.write_text(json.dumps(results,indent=2));print(key+' '+results[key]['status'],flush=True)
 # Public issuer mapping, then bounded historical source documents. No guessed CIKs.
 try:
  mapping=await p.request('sec','https://www.sec.gov/files/company_tickers.json',headers={'User-Agent':p.cfg['SEC_USER_AGENT']});by_symbol={r['ticker']:str(r['cik_str']) for r in mapping.values()};db.set_setting('universe_ciks',{s:by_symbol[s] for s in stocks if s in by_symbol})
  chosen=[s for s in ['PLTR','JPM','XOM','JNJ','CAT','NEE','WMT','SOFI','RKLB','HIMS','FIX','STRL','CALM','INDB','OZK','FULT'] if s in by_symbol]
  for s in chosen:
   key='sec_'+s
   if results.get(key,{}).get('complete_window'):continue
   try:results[key]=await h.sec_form4(s,by_symbol[s],100)
   except Exception as e:results[key]={'status':getattr(e,'status',type(e).__name__)}
   path.write_text(json.dumps(results,indent=2));print(key+' '+str(results[key].get('downloaded',results[key].get('status'))),flush=True)
 except Exception as e:results['sec_mapping']={'status':getattr(e,'status',type(e).__name__)}
 results['completed_at']=now().isoformat();path.write_text(json.dumps(results,indent=2));db.set_setting('product_expansion',results);db.set_setting('universe_coverage_cache',{});print('Expansion finished',flush=True)
if __name__=='__main__':asyncio.run(main())
