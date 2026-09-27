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
import { Overview, Scanner, Asset } from "./MarketViews";
import { AISettingsView } from "./AISettingsView";
import { Providers } from "./Providers";
import { Research } from "./Research";
import { Portfolio, Risk, Orders } from "./PortfolioViews";
import { Options, Intelligence } from "./IntelligenceViews";
import { Chat } from "./Chat";
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
      ["social", "Social & viral", MessageSquare],
      ["options", "Options", Layers3],
      ["prediction-markets", "Prediction markets", BarChart3],
      ["crypto", "Crypto", Zap],
      ["themes", "Themes & relationships", Network],
      ["macro", "Macro & energy", Globe2],
    ],
  },
  {
    name: "RESEARCH",
    items: [
      ["research", "Research lab", FlaskConical],
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
  const [chat, setChat] = useState(false);
  const refresh = useCallback(async () => {
    try {
      setOverview(await api("/overview"));
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 15000);
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
        "Overview";
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
        <nav>
          {groups.map((g) => (
            <div key={g.name} className="nav-group">
              <div className="nav-label">{g.name}</div>
              {g.items.map(([path, label, Icon]) => {
                const I = Icon as typeof Activity;
                return (
                  <Link
                    key={String(path)}
                    aria-label={String(label)}
                    href={"/" + path}
                    className={page === path ? "nav-item active" : "nav-item"}
                  >
                    <I size={16} />
                    <span>{String(label)}</span>
                    {path === "" && <span className="nav-dot" />}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>
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
          <div className="top-right">
            <Badge tone="green">
              <span className="status-dot" /> INTERNAL PAPER
            </Badge>
            <button
              className="icon-button"
              aria-label="Open chatbot"
              onClick={() => setChat(true)}
            >
              <MessageSquare size={18} />
            </button>
            <span className="avatar small">IL</span>
          </div>
        </header>
        <main>
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
          {!overview ? (
            <Empty title="Connecting to TraderX">
              Start the backend at localhost:8000 to load your workspace.
            </Empty>
          ) : (
            <>
              {!page && (
                <Overview
                  data={overview}
                  healthy={healthy}
                  onInspect={setInspect}
                />
              )}
              {page === "scanner" && <Scanner data={overview} />}
              {page === "asset" && (
                <Asset symbol={assetSymbol} onInspect={setInspect} />
              )}
              {page === "settings" && (
                <AISettingsView data={overview.ai} act={act} />
              )}
              {page === "providers" && <Providers data={overview} act={act} />}
              {[
                "research",
                "experiments",
                "backtests",
                "models",
                "strategies",
              ].includes(page) && (
                <Research page={page} act={act} onInspect={setInspect} />
              )}
              {page === "risk" && (
                <Risk data={overview} act={act} onInspect={setInspect} />
              )}
              {page === "portfolio" && <Portfolio data={overview} act={act} />}
              {page === "orders" && <Orders act={act} onInspect={setInspect} />}
              {page === "options" && <Options act={act} />}
              {[
                "earnings",
                "insiders",
                "institutions",
                "themes",
                "social",
                "macro",
                "crypto",
                "prediction-markets",
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
      {chat && (
        <Chat
          onClose={() => setChat(false)}
          provider={overview?.ai.current_provider || "off"}
        />
      )}
    </div>
  );
}
