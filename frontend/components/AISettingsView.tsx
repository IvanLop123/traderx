"use client";
import { useState } from "react";
import { api, number } from "@/lib/api";
import { Panel, Stat } from "./Common";
type Data = Record<string, any>;
export function AISettingsView({ data, act }: { data: Data; act: any }) {
  const [settings, setSettings] = useState<Data>(data.settings);
  const [local, setLocal] = useState<Data>(data.local_status);
  const [saving, setSaving] = useState(false);
  const set = (key: string, value: any) =>
    setSettings((s) => ({ ...s, [key]: value }));
  const save = async () => {
    setSaving(true);
    await act(
      () => api("/settings/ai", settings, "PUT"),
      "AI configuration saved safely",
    );
    setSaving(false);
  };
  return (
    <>
      <div className="stats">
        <Stat
          label="CURRENT PROVIDER"
          value={data.current_provider.toUpperCase()}
          detail={data.current_model || "No model active"}
        />
        <Stat
          label="TODAY · API BILLING"
          value={"$" + data.usage.daily_cost.toFixed(5)}
          detail={"Budget $" + settings.daily_budget}
        />
        <Stat
          label="THIS MONTH · API BILLING"
          value={"$" + data.usage.monthly_cost.toFixed(5)}
          detail={"Budget $" + settings.monthly_budget}
        />
        <Stat
          label="CALLS / TOKENS"
          value={
            data.usage.calls +
            " / " +
            number(data.usage.input_tokens + data.usage.output_tokens, 0)
          }
          detail="All providers · persistent usage ledger"
        />
      </div>
      <Panel
        title="Choose your AI provider"
        eyebrow="OPTIONAL TEXT INTELLIGENCE"
      >
        <div className="provider-options">
          {[
            ["off", "AI Off", "All quantitative systems stay active."],
            ["local", "Local AI", "Use a model running on this Mac."],
            ["openai", "Cloud AI", "Metered API text extraction with budget limits."],
            ["hybrid", "Hybrid", "Local first. Explicit escalation only."],
          ].map(([key, label, desc]) => (
            <button
              key={key}
              className={
                "provider-choice " + (settings.provider === key ? "chosen" : "")
              }
              onClick={() => set("provider", key)}
            >
              <span className="radio" />
              <strong>{label}</strong>
              <small>{desc}</small>
            </button>
          ))}
        </div>
        <div className="settings-grid">
          <label className="toggle-row">
            <div>
              <strong>Automated AI analysis</strong>
              <small>Relevant new text documents only</small>
            </div>
            <input
              type="checkbox"
              checked={settings.automated}
              onChange={(e) => set("automated", e.target.checked)}
            />
          </label>
          <label className="toggle-row">
            <div>
              <strong>Allow automated cloud AI calls</strong>
              <small>Requires automation and available budget</small>
            </div>
            <input
              type="checkbox"
              checked={settings.openai_automated}
              onChange={(e) => set("openai_automated", e.target.checked)}
            />
          </label>
          <label className="toggle-row">
            <div>
              <strong>Cloud escalation</strong>
              <small>Only explicitly difficult, allowlisted tasks</small>
            </div>
            <input
              type="checkbox"
              checked={settings.escalation}
              onChange={(e) => set("escalation", e.target.checked)}
            />
          </label>
          <div className="toggle-row">
            <div>
              <strong>Local model status</strong>
              <small>{local.status}</small>
            </div>
            <button
              className="button secondary"
              onClick={async () => {
                const r = await act(
                  () => api("/settings/ai/local-health", {}),
                  "Local endpoint checked",
                );
                if (r) setLocal(r);
              }}
            >
              Check connection
            </button>
          </div>
        </div>
      </Panel>
      <div className="two-col">
        <Panel title="Model configuration">
          <div className="form-grid">
            <label>
              Local endpoint
              <input
                value={settings.local_base_url}
                onChange={(e) => set("local_base_url", e.target.value)}
              />
            </label>
            <label>
              Local model identifier
              <input
                placeholder="Exact model loaded in LM Studio"
                value={settings.local_model}
                onChange={(e) => set("local_model", e.target.value)}
              />
            </label>
            <label>
              Cloud model
              <input
                list="cloud-models"
                value={settings.openai_model}
                onChange={(e) => set("openai_model", e.target.value)}
              />
            </label>
            <label>
              Escalation model
              <input
                list="cloud-models"
                placeholder="Disabled until explicitly configured"
                value={settings.escalation_model}
                onChange={(e) => set("escalation_model", e.target.value)}
              />
            </label>
          </div>
          <datalist id="cloud-models">{["gpt-5.4-nano-2026-03-17","gpt-6-luna","gpt-6.1-sol","gpt-6-astra"].map(model=><option key={model} value={model}/>)}</datalist>
          <p className="panel-note">
            Keys stay in the backend .env file. Local servers do not need a key
            unless you enabled authentication. Unpriced Cloud models are
            blocked until their rates are configured.
          </p>
        </Panel>
        <Panel title="Budget & rate limits">
          <div className="form-grid">
            {[
              ["daily_budget", "Daily budget (USD)"],
              ["monthly_budget", "Monthly budget (USD)"],
              ["calls_per_hour", "Maximum calls per hour"],
              ["max_output_tokens", "Maximum output tokens"],
            ].map(([key, label]) => (
              <label key={key}>
                {label}
                <input
                  type="number"
                  min="0"
                  step={key.includes("budget") ? ".01" : "1"}
                  value={settings[key]}
                  onChange={(e) => set(key, Number(e.target.value))}
                />
              </label>
            ))}
          </div>
          <div className="callout">
            <p>
              {data.openai_budget_paused
                ? "API analysis is paused by the budget or rate gate."
                : "API budget reservations are checked before each request."}{" "}
              Market ingestion, signals and portfolio accounting continue
              independently.
            </p>
          </div>
        </Panel>
      </div>
      <div className="save-bar">
        <span>
          Provider changes apply to new requests. In-flight calls finish under
          their existing reservation.
        </span>
        <button className="button primary" disabled={saving} onClick={save}>
          Save AI settings
        </button>
      </div>
      <Panel title="Usage by module">
        <div className="metric-list">
          {Object.entries(data.usage.by_module).map(([k, v]: [string, any]) => (
            <div key={k}>
              <span>{k}</span>
              <strong>
                {v.calls} calls · {number(v.tokens)} tokens · $
                {v.estimated_cost.toFixed(5)}
              </strong>
            </div>
          ))}
          {!Object.keys(data.usage.by_module).length && (
            <p className="panel-note">No AI calls have been made.</p>
          )}
        </div>
      </Panel>
    </>
  );
}
