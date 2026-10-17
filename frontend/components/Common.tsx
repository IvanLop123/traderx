"use client";
import { ReactNode } from "react";
import { ChevronRight, FileText, Layers3 } from "lucide-react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import { money, number, date } from "@/lib/api";
type Data = Record<string, any>;
export function Badge({
  children,
  tone = "",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return <span className={"badge " + tone}>{children}</span>;
}

export function Empty({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Layers3 size={25} />
      </div>
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}

export function Panel({
  title,
  eyebrow,
  children,
  action,
}: {
  title: string;
  eyebrow?: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          {eyebrow && <div className="eyebrow">{eyebrow}</div>}
          <h2>{title}</h2>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

export function Stat({
  label,
  value,
  detail,
  positive = false,
}: {
  label: string;
  value: string;
  detail: string;
  positive?: boolean;
}) {
  return (
    <div className="stat">
      <span>{label}</span>
      <strong className={positive ? "positive" : ""}>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

export function Plot({
  data,
  value = "close",
  second,
  height = 250,
}: {
  data: Data[];
  value?: string;
  second?: string;
  height?: number;
}) {
  return (
    <div style={{ height, width: "100%" }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={data}
          margin={{ top: 12, right: 10, bottom: 0, left: 2 }}
        >
          <defs>
            <linearGradient id="fade" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#b48768" stopOpacity={0.22} />
              <stop offset="95%" stopColor="#b48768" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid
            vertical={false}
            stroke="#44342b"
            strokeDasharray="3 5"
          />
          <XAxis
            dataKey="timestamp"
            minTickGap={70}
            tickFormatter={(v) =>
              new Date(v).toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
              })
            }
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#b9aaa0", fontSize: 10 }}
          />
          <YAxis
            domain={["auto", "auto"]}
            width={65}
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#b9aaa0", fontSize: 10 }}
            tickFormatter={(v) => number(v, 0)}
          />
          <Tooltip
            labelFormatter={(v) => date(String(v))}
            formatter={(v) => money(Number(v))}
            contentStyle={{
              background: "#211915",
              border: "1px solid #634b3d",
              borderRadius: 8,
              color: "#f2eae4",
            }}
          />
          <Area
            type="monotone"
            dataKey={value}
            stroke="#b48768"
            fill="url(#fade)"
            strokeWidth={2}
            isAnimationActive={false}
          />
          {second && (
            <Area
              type="monotone"
              dataKey={second}
              stroke="#a8adb9"
              fill="none"
              strokeWidth={1.5}
              isAnimationActive={false}
            />
          )}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function JsonView({ value }: { value: any }) {
  return <pre className="json">{JSON.stringify(value, null, 2)}</pre>;
}

export function Records({
  records,
  onInspect,
}: {
  records: Data[];
  onInspect: (v: Data) => void;
}) {
  return records.length ? (
    <div className="record-list">
      {records.map((r) => (
        <button className="record" key={r.id} onClick={() => onInspect(r)}>
          <span className="record-icon">
            <FileText size={17} />
          </span>
          <span>
            <strong>
              {r.payload.title ||
                r.payload.symbol ||
                r.symbol ||
                r.payload.model ||
                r.payload.series ||
                r.kind.replaceAll("_", " ")}
            </strong>
            <small>
              {r.payload.provider || r.payload.source || "Local research"} ·{" "}
              {date(r.created_at)}
            </small>
          </span>
          <Badge>{r.kind.replaceAll("_", " ")}</Badge>
          <ChevronRight size={16} />
        </button>
      ))}
    </div>
  ) : (
    <Empty title="No evidence collected yet">
      Connect a provider or import a source document. Records will appear here
      with their original source and observation time.
    </Empty>
  );
}
