"use client";
import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BarChart3,
  BookOpen,
  Boxes,
  ChevronRight,
  FileText,
  FlaskConical,
  Globe2,
  Layers3,
  LayoutDashboard,
  Loader2,
  MessageSquare,
  Network,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Wallet,
  X,
  Zap,
} from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Empty, JsonView } from "./Common";
import { AISettingsView } from "./AISettingsView";
import { Providers } from "./Providers";
import { Research } from "./Research";
import {AutonomousResearch} from "./AutonomousResearch";
import { Risk } from "./PortfolioViews";
import { Options, Intelligence } from "./IntelligenceViews";
import { NewsEvents } from "./NewsEvents";
import { SystemResearch } from "./SystemResearch";
import { DataCoverage } from "./DataCoverage";
import {DecisionDiagnostics,ForwardEvidence} from "./Qualification";
import { ForwardStudies } from "./ForwardStudies";
import {GlobalAssetSearch,AssetHistory,PersonalOrders,PaperSettings} from "./PaperProduct";
import {ModelPortfolioView,StrategyRegistry} from "./ModelPortfolio";
import {CockpitOverview,CockpitScanner,CockpitAsset,CockpitPortfolio,TradeIdeas} from "./DecisionCockpit";
import {MarketStructure} from "./MarketStructure";
import {AlphaResearch} from "./AlphaResearch";
import {AdvancedResearch,ShadowPortfolioView} from "./AdvancedResearch";
type Data = Record<string, any>;
const groups = [
  {
    name: "WORKSPACE",
    items: [
      ["", "Overview", LayoutDashboard],
      ["scanner", "Market scanner", Search],
      ["portfolio", "Portfolio", Wallet],
      ["orders", "Orders", Layers3],
    ],
  },
  {
    name: "INTELLIGENCE",
    items: [
      ["insiders", "Insiders", Activity],
      ["earnings", "Earnings", FileText],
      ["institutions", "Institutions", Boxes],
      ["traders", "Public traders", Globe2],
      ["options", "Options", Layers3],
      ["crypto", "Crypto", Zap],
      ["themes", "Themes & relationships", Network],
      ["macro", "Macro & energy", Globe2],
    ],
  },
  {
    name: "RESEARCH",
    items: [
      ["research", "Research lab", FlaskConical],
      ["autonomous-research", "Autonomous Research", FlaskConical],
      ["advanced-research", "Advanced Research", FlaskConical],
      ["alpha-library", "Alpha library", FlaskConical],
      ["market-structure", "Market structure", FlaskConical],
      ["experiments", "Experiments", BookOpen],
      ["backtests", "Backtests", BarChart3],
      ["models", "Models", Boxes],
      ["strategies", "Strategies", Layers3],
    ],
  },
  {
    name: "SYSTEM",
    items: [
      ["risk", "Risk controls", ShieldCheck],
      ["providers", "System health", Activity],
      ["settings", "Settings", Settings2],
    ],
  },
];
export default function Dashboard() {
  const pathname = usePathname();
  const page = pathname.split("/")[1] || "";
  const assetSymbol = decodeURIComponent(pathname.split("/")[2] || "BTC-USD");
  const [overview, setOverview] = useState<Data | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [inspect, setInspect] = useState<Data | null>(null);
  const refresh = useCallback(async () => {
    try {
      if (["settings","providers","system","risk"].includes(page)) setOverview(await api("/overview"));
      else setOverview({providers:await api("/providers")});
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }, [page]);
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 60000);
    return () => clearInterval(timer);
  }, [refresh]);
  const act = async (fn: () => Promise<any>, success = "Saved") => {
    setBusy(true);
    setNotice("");
    try {
      const result = await fn();
      setNotice(success);
      await refresh();
      return result;
    } catch (e) {
      setError((e as Error).message);
      return null;
    } finally {
      setBusy(false);
    }
  };
  const title =
    page === "asset"
      ? assetSymbol
      : groups.flatMap((g) => g.items).find((i) => i[0] === page)?.[1] ||
        ({"shadow-portfolio":"Experimental Shadow Portfolio","alpha-library":"Alpha library & allocation","advanced-research":"Advanced Research","trade-ideas":"My Trade Ideas",watchlist:"Watchlist",assets:"Assets",system:"System",coverage:"Data coverage",workers:"Workers","forward-studies":"Forward studies","model-portfolio":"Model Paper Portfolio","forward-evidence":"Forward Evidence","decision-diagnostics":"Decision diagnostics"}[page]||"Overview");
  const researchPages=['research','autonomous-research','alpha-library','advanced-research','market-structure','backtests','experiments','strategies','insiders','institutions','earnings','macro','themes','traders','options'];
  const section=researchPages.includes(page)?'research':['providers','coverage','workers'].includes(page)?'system':['portfolio','shadow-portfolio','orders','risk','forward-studies','model-portfolio','forward-evidence','decision-diagnostics'].includes(page)?'portfolio':['asset','assets','crypto','watchlist','trade-ideas'].includes(page)?'assets':page;
  const primary=[['','Overview',LayoutDashboard],['scanner','Scanner',Search],['assets','Assets',BarChart3],['portfolio','Portfolio',Wallet],['models','Models',Boxes],['research','Research',FlaskConical],['system','System',Activity],['settings','Settings',Settings2]];
  const subitems=section==='research'?researchPages.map(p=>[p,String(groups.flatMap(g=>g.items).find(i=>i[0]===p)?.[1]||p)]):section==='system'||page==='system'?[['providers','Provider health'],['coverage','Data coverage'],['workers','Workers']]:section==='portfolio'?[['shadow-portfolio','Experimental Shadow'],['model-portfolio','Qualified Model Paper'],['portfolio','My Manual Portfolio'],['forward-evidence','Forward Evidence'],['decision-diagnostics','Decision diagnostics'],['forward-studies','Scientific studies'],['orders','Orders'],['risk','Risk controls']]:section==='assets'?[['assets','Asset list'],['watchlist','Watchlist'],['trade-ideas','My Trade Ideas'],['crypto','Crypto context']]:[];
  const providers = overview?.providers || [];
  const healthy = providers.filter((p: Data) =>
    p.status.startsWith("WORKING"),
  ).length;
  return (
    <div className="shell">
      <aside className="sidebar">
        <Link className="brand" href="/">
          <div className="brand-mark">
            T<span>↗</span>
          </div>
          TRADER<span>X</span>
          <small>RESEARCH TERMINAL</small>
        </Link>
        <div className="workspace">
          <span className="avatar">IL</span>
          <div>
            Personal workspace<small>Local · Paper environment</small>
          </div>
          <ChevronRight size={14} />
        </div>
        <nav aria-label="Primary navigation">{primary.map(([path,label,Icon])=>{const I=Icon as typeof Activity;return <Link key={String(path)} title={String(label)} aria-label={String(label)} href={'/'+path} className={section===path||(page==='system'&&path==='system')?'nav-item active':'nav-item'}><I size={18}/><span>{String(label)}</span></Link>})}</nav>
        <div className="sidebar-foot">
          <span className="status-dot" /> Deterministic engine
          <small>AI is optional. Your research stays running.</small>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <ChevronRight size={12} /> <span>{String(title)}</span>
          </div>
          <GlobalAssetSearch/>
          <div className="top-right">
            <Badge tone="green">
              <span className="status-dot" /> INTERNAL PAPER
            </Badge>

            <span className="avatar small">IL</span>
          </div>
        </header>
        <main>
          {subitems.length>0&&<nav className="subnav" aria-label="Section navigation">{subitems.map(([path,label])=><Link key={path} href={"/"+path} aria-current={page===path?"page":undefined}>{label}</Link>)}</nav>}
          <div className="page-heading">
            <div className="eyebrow">
              TRADERX / {page ? "WORKSPACE" : "MARKET INTELLIGENCE"}
            </div>
            <div className="heading-row">
              <div>
                <h1>
                  {String(title)}
                  {!page && <span className="live-label">LOCAL</span>}
                </h1>
                <p>
                  {!page
                    ? "Your market, connected. Evidence first. Every decision accountable."
                    : page === "settings"
                      ? "Choose how intelligence runs. You stay in control of every API dollar."
                      : "Explore the evidence. Test the hypothesis. Understand the risk."}
                </p>
              </div>
              <button
                className="button secondary"
                disabled={busy}
                onClick={() =>
                  act(() => api("/market/refresh", {}), "Market data refreshed")
                }
              >
                {busy ? (
                  <Loader2 className="spin" size={15} />
                ) : (
                  <RefreshCw size={15} />
                )}{" "}
                Refresh data
              </button>
            </div>
          </div>
          {error && (
            <div className="banner error" role="alert">
              {error}
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <X size={15} />
              </button>
            </div>
          )}
          {notice && (
            <div className="banner success" role="status">
              {notice}
              <button
                aria-label="Dismiss notification"
                onClick={() => setNotice("")}
              >
                <X size={15} />
              </button>
            </div>
          )}
          {!overview && ["settings","providers","system","risk"].includes(page) ? (
            <Empty title="Connecting to TraderX">
              Loading your saved workspace and current data. If this takes longer than a few seconds, open TraderX.command and retry.
            </Empty>
          ) : (
            <>
              {!page && (
                <><CockpitOverview/><NewsEvents/></>
              )}
              {page === "scanner" && <CockpitScanner/>}
              {page === "assets" && <CockpitScanner/>}
              {page === "advanced-research" && <AdvancedResearch/>}
              {page === "alpha-library" && <AlphaResearch/>}
              {page === "market-structure" && <MarketStructure/>}
          {page === "shadow-portfolio" && <ShadowPortfolioView/>}
          {page === "model-portfolio" && <ModelPortfolioView/>}
              {page === "strategies" && <StrategyRegistry/>}
              {page === "watchlist"&&<CockpitScanner watchOnly/>}
              {page === "asset" && (
                <><AssetHistory key={assetSymbol} symbol={assetSymbol}/><CockpitAsset key={assetSymbol+"-view"} symbol={assetSymbol}/><NewsEvents symbol={assetSymbol}/></>
              )}
              {page === "settings" && (
                <><PaperSettings/><AISettingsView data={overview?.ai} act={act} /></>
              )}
              {["providers","system"].includes(page) && <Providers data={overview!} act={act} />}
              {page === "workers"&&<SystemResearch/>}
              {page === "coverage"&&<DataCoverage/>}
              {page === "forward-studies"&&<ForwardStudies/>}
              {page === "forward-evidence"&&<ForwardEvidence/>}
              {page === "decision-diagnostics"&&<DecisionDiagnostics/>}
              {[
                "research",
                "experiments",
                "backtests",
                "models",
              ].includes(page) && (
                <Research page={page} act={act} onInspect={setInspect} />
              )}
              {page === "autonomous-research" && <AutonomousResearch/>}
              {page === "risk" && (
                <Risk data={overview!} act={act} onInspect={setInspect} />
              )}
              {page === "portfolio" && <CockpitPortfolio />}
              {page === "orders" && <PersonalOrders />}{page === "trade-ideas"&&<TradeIdeas/>}
              {page === "options" && <Options act={act} />}
              {[
                "earnings",
                "insiders",
                "institutions",
                "themes",
                "macro",
                "crypto",
                "traders",
              ].includes(page) && (
                <Intelligence page={page} act={act} onInspect={setInspect} />
              )}
            </>
          )}
          <footer>
            <span>
              <span className="status-dot" /> LOCAL WORKSPACE <b>·</b> {healthy}{" "}
              providers connected
            </span>
            <span>
              Research ≠ prediction ≠ order <b>·</b> Live execution disabled
            </span>
          </footer>
        </main>
      </div>
      {inspect && (
        <div className="overlay" onClick={() => setInspect(null)}>
          <section className="drawer" onClick={(e) => e.stopPropagation()}>
            <div className="panel-head">
              <div>
                <div className="eyebrow">TRACEABLE EVIDENCE</div>
                <h2>Source & provenance</h2>
              </div>
              <button
                className="icon-button"
                aria-label="Close evidence"
                onClick={() => setInspect(null)}
              >
                <X />
              </button>
            </div>
            <p className="muted">
              Original values, source references, timestamps and model metadata
              are preserved for review.
            </p>
            {inspect.kind === "document" &&
              !["form4", "13f"].includes(inspect.payload.kind) && (
                <button
                  className="button primary"
                  onClick={async () => {
                    const r = await act(
                      () => api("/documents/" + inspect.id + "/analyze", {}),
                      "Text analysis request completed",
                    );
                    if (r) setInspect(r);
                  }}
                >
                  Analyze this text
                </button>
              )}
            <JsonView value={inspect} />
          </section>
        </div>
      )}

    </div>
  );
}
