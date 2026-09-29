"use client";
import { useEffect, useState } from "react";
import { ErrorBox, PageHead, Pill } from "@/components/ui";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate } from "@/lib/format";
import { kg, ksh } from "@/lib/planning";

type Out = { school: string; commodity: string; on_hand: number; daily_use: number | null; days_left: number | null; stockout_on: string | null; basis: string; risk: string | null };
type Req = { commodity_code: string; commodity: string; unit: string; planned_last_term: number; accepted: number; used: number; on_hand_at_schools: number;
  suggested_next_term: number; estimated_value: number | null };
type Price = { commodity_code: string; commodity: string; contracts: number; min: number; median: number; max: number; weighted_avg: number | null; latest: number;
  reference_price: number | null; latest_vs_reference_pct: number | null; trend_pct: number | null;
  points: { date: string; contract: string; county: string; supplier: string; unit_price: number; quantity: number; vs_median_pct: number | null }[] };

function Range({ p }: { p: Price }) {
  const lo = Math.min(p.min, p.reference_price ?? p.min), hi = Math.max(p.max, p.reference_price ?? p.max), span = hi - lo || 1;
  const x = (v: number) => `${((v - lo) / span) * 100}%`;
  return <div title={`min ${p.min} · median ${p.median} · max ${p.max}`} style={{ position: "relative", height: 16, minWidth: 140 }}>
    <div style={{ position: "absolute", top: 7, left: x(p.min), width: `calc(${x(p.max)} - ${x(p.min)})`, height: 2, background: "#B9C2AC" }} />
    <div style={{ position: "absolute", top: 3, left: x(p.median), width: 10, height: 10, marginLeft: -5, borderRadius: 5, background: "var(--green)" }} />
    {p.reference_price != null && <div style={{ position: "absolute", top: 0, left: x(p.reference_price), width: 2, height: 16, background: "#8A5A00" }} />}
  </div>;
}

export default function Insights() {
  const { can } = useAuth();
  const [tab, setTab] = useState<"stock" | "req" | "prices">("stock");
  const [out, setOut] = useState<Out[]>([]);
  const [req, setReq] = useState<Req[]>([]);
  const [prices, setPrices] = useState<Price[]>([]);
  const [err, setErr] = useState<unknown>(null);
  useEffect(() => {
    get<Out[]>("/analytics/stock-outlook").then(setOut).catch(setErr);
    if (can("dem:view", "meal:view")) get<Req[]>("/analytics/requirements").then(setReq).catch(() => {});
    if (can("src:view", "con:view", "meal:view")) get<Price[]>("/analytics/prices").then(setPrices).catch(() => {});
  }, [can]);
  return (
    <>
      <PageHead crumb="Performance" title="Forecasts & price intelligence" sub="Simple, explainable projections from platform records: days of stock left, next-term requirements and contract price ranges." />
      <div className="tabs">
        <button className={`tab ${tab === "stock" ? "on" : ""}`} onClick={() => setTab("stock")}>Stock-out outlook</button>
        {!!req.length && <button className={`tab ${tab === "req" ? "on" : ""}`} onClick={() => setTab("req")}>Next-term requirements</button>}
        {!!prices.length && <button className={`tab ${tab === "prices" ? "on" : ""}`} onClick={() => setTab("prices")}>Prices</button>}
      </div>
      <ErrorBox error={err} />
      {tab === "stock" && <div className="card"><div className="tablewrap"><table>
        <thead><tr><th>School</th><th>Commodity</th><th className="r">On hand</th><th className="r">Daily use</th><th className="r">Days left</th><th>Runs out</th><th>Based on</th></tr></thead>
        <tbody>{out.map((o, i) => <tr key={i}><td>{o.school}</td><td>{o.commodity}</td><td className="r num">{kg(o.on_hand)}</td><td className="r num">{o.daily_use != null ? kg(o.daily_use) : "—"}</td>
          <td className="r num">{o.days_left ?? "—"} {o.risk && <Pill status={o.risk} label={o.risk === "high" ? "Urgent" : "Soon"} />}</td><td className="small">{fmtDate(o.stockout_on)}</td>
          <td className="small muted">{o.days_left == null ? "No use or plan recorded" : o.basis}</td></tr>)}
          {!out.length && <tr><td colSpan={7} className="muted">No school stock recorded yet.</td></tr>}</tbody></table></div>
        <p className="small muted" style={{ marginTop: 8 }}>Daily use = food recorded as used in the last 30 days ÷ 30, or the approved demand plan ÷ feeding days when no use is recorded. Recalled stock is excluded.</p></div>}
      {tab === "req" && <div className="card"><div className="tablewrap"><table>
        <thead><tr><th>Commodity</th><th className="r">Planned (last approved)</th><th className="r">Accepted at schools</th><th className="r">Used</th><th className="r">In school stores</th><th className="r">Suggested next term</th><th className="r">At reference price</th></tr></thead>
        <tbody>{req.map((r) => <tr key={r.commodity_code}><td>{r.commodity}</td><td className="r num">{kg(r.planned_last_term, r.unit)}</td><td className="r num">{kg(r.accepted, r.unit)}</td>
          <td className="r num">{kg(r.used, r.unit)}</td><td className="r num">{kg(r.on_hand_at_schools, r.unit)}</td><td className="r num"><b>{kg(r.suggested_next_term, r.unit)}</b></td>
          <td className="r num">{r.estimated_value != null ? ksh(r.estimated_value) : "—"}</td></tr>)}</tbody></table></div>
        <p className="small muted" style={{ marginTop: 8 }}>Suggested = the latest approved school plans minus what is already in school stores. Schools still submit and approve their own demand; this is a planning check.</p></div>}
      {tab === "prices" && <div className="card"><div className="tablewrap"><table>
        <thead><tr><th>Commodity</th><th className="r">Contracts</th><th>Range (● median, | reference)</th><th className="r">Median</th><th className="r">Latest</th><th className="r">vs reference</th><th className="r">Trend</th></tr></thead>
        <tbody>{prices.map((p) => <tr key={p.commodity_code}><td>{p.commodity}</td><td className="r num">{p.contracts}</td><td><Range p={p} /></td>
          <td className="r num">{p.median.toLocaleString()}</td><td className="r num">{p.latest.toLocaleString()}</td>
          <td className="r num">{p.latest_vs_reference_pct != null ? `${p.latest_vs_reference_pct > 0 ? "+" : ""}${p.latest_vs_reference_pct}%` : "—"}</td>
          <td className="r num">{p.trend_pct != null ? `${p.trend_pct > 0 ? "+" : ""}${p.trend_pct}%` : "—"}</td></tr>)}</tbody></table></div>
        <p className="small muted" style={{ marginTop: 8 }}>Unit prices (KSh) from awarded contracts in your area. Reference prices are the planning estimates in master data.</p></div>}
    </>
  );
}
