"use client";
import { useCallback, useEffect, useState } from "react";
import { ErrorBox, PageHead } from "@/components/ui";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { pct } from "@/lib/finance";
import { kg, ksh } from "@/lib/planning";

type Share = { value: number; pct: number | null };
type Dash = {
  scope: string; counties: { id: string; name: string }[];
  reach: { schools_served: number; learners_in_served_schools: number; meals_served_recorded: number };
  food: { delivered_kg: number; accepted_kg: number; acceptance_pct: number | null; on_time_pct: number | null; deliveries: number; by_commodity: { commodity: string; accepted_kg: number }[] };
  sourcing: { po_value: number; orders: number; local_share: Share; smallholder_share: Share; inclusive_share: Share; producers: number;
    women_producers_pct: number | null; youth_producers_pct: number | null; sourced_kg: number };
  finance: { paid: number; avg_days_to_pay: number | null; invoices_pending: number; pending_value: number };
  accountability: { open_exceptions: number; overdue_exceptions: number; complaints: number; complaints_resolved_in_sla_pct: number | null };
  monthly: { month: string; delivered_kg: number; paid: number }[];
};

function Tile({ label, value, note, tone = "" }: { label: string; value: React.ReactNode; note?: string; tone?: string }) {
  return <div className={`card kpi ${tone}`}><div className="l">{label}</div><div className="v">{value}</div>{note && <div className="small muted">{note}</div>}</div>;
}

/** Single-series bar chart: one hue, rounded data ends, hover readout, values in text ink. */
function Bars({ data, fmt, label, vertical = false }: { data: { k: string; v: number }[]; fmt: (n: number) => string; label: string; vertical?: boolean }) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(1, ...data.map((d) => d.v));
  if (!data.length) return <p className="small muted">No data for this period yet.</p>;
  if (vertical) return (
    <div role="img" aria-label={label}>
      <div className="small" style={{ minHeight: 18 }}>{hover != null ? <><b>{data[hover].k}</b>: {fmt(data[hover].v)}</> : <span className="muted">Hover a bar for its value</span>}</div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 150, borderBottom: "1px solid var(--line)", padding: "0 2px" }}>
        {data.map((d, i) => <div key={d.k} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} title={`${d.k}: ${fmt(d.v)}`}
          style={{ flex: 1, height: "100%", display: "flex", alignItems: "flex-end", cursor: "default" }}>
          <div style={{ width: "100%", maxWidth: 38, margin: "0 auto", height: `${Math.max(1, (d.v / max) * 100)}%`, background: "var(--green)", opacity: hover == null || hover === i ? 1 : 0.55, borderRadius: "4px 4px 0 0" }} /></div>)}
      </div>
      <div style={{ display: "flex", gap: 2 }}>{data.map((d) => <div key={d.k} className="small muted" style={{ flex: 1, textAlign: "center" }}>{d.k}</div>)}</div>
    </div>);
  return (
    <div role="img" aria-label={label} className="stack" style={{ gap: 6 }}>
      {data.map((d, i) => <div key={d.k} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} style={{ display: "grid", gridTemplateColumns: "150px 1fr 110px", gap: 10, alignItems: "center", marginTop: 6 }}>
        <span className="small">{d.k}</span>
        <div style={{ height: 12, background: "#EEF0E9", borderRadius: 4 }}><div style={{ width: `${Math.max(1, (d.v / max) * 100)}%`, height: "100%", background: "var(--green)", borderRadius: "0 4px 4px 0", opacity: hover == null || hover === i ? 1 : 0.55 }} /></div>
        <span className="small num r">{fmt(d.v)}</span></div>)}
    </div>);
}

export default function Meal() {
  const { can } = useAuth();
  const [d, setD] = useState<Dash | null>(null);
  const [county, setCounty] = useState("");
  const [start, setStart] = useState(""); const [end, setEnd] = useState("");
  const [exportsList, setExports] = useState<{ key: string; label: string }[]>([]);
  const [table, setTable] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const load = useCallback(() => {
    const q = new URLSearchParams(); if (county) q.set("county_id", county); if (start) q.set("start", start); if (end) q.set("end", end);
    get<Dash>(`/meal/dashboard?${q}`).then(setD).catch(setErr);
  }, [county, start, end]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (can("meal:export")) get<typeof exportsList>("/meal/exports").then(setExports).catch(() => {}); }, [can]);
  const month = (m: string) => new Date(`${m}-01T00:00:00`).toLocaleDateString("en-KE", { month: "short", year: "2-digit" });
  return (
    <>
      <PageHead crumb="Performance" title="MEAL dashboard" sub={`Programme indicators calculated from platform records${d ? ` · ${d.scope}` : ""}. Figures cover only what has been recorded here.`}>
        <select className="btn" value={county} onChange={(e) => setCounty(e.target.value)} aria-label="County"><option value="">All my counties</option>
          {d?.counties.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
        <input className="btn" type="date" aria-label="From" value={start} onChange={(e) => setStart(e.target.value)} />
        <input className="btn" type="date" aria-label="To" value={end} onChange={(e) => setEnd(e.target.value)} />
      </PageHead>
      <ErrorBox error={err} />
      {d && <div className="stack">
        <h2>Reach</h2>
        <div className="grid g3">
          <Tile label="Schools receiving food" value={d.reach.schools_served} />
          <Tile label="Learners in those schools" value={d.reach.learners_in_served_schools.toLocaleString()} note="Enrolment from school demand plans" tone="leaf" />
          <Tile label="Meals served (recorded)" value={d.reach.meals_served_recorded.toLocaleString()} note="From school stock-use records" tone="gold" />
        </div>
        <h2>Food delivered</h2>
        <div className="grid g4">
          <Tile label="Accepted at schools" value={kg(d.food.accepted_kg)} note={`${d.food.deliveries} confirmed deliveries`} />
          <Tile label="Acceptance rate" value={pct(d.food.acceptance_pct)} note={`of ${kg(d.food.delivered_kg)} delivered`} tone="leaf" />
          <Tile label="On-time deliveries" value={pct(d.food.on_time_pct)} note="Received by the planned date + 1 day" tone="gold" />
          <Tile label="Sourced from producers" value={kg(d.sourcing.sourced_kg)} note="Farmer intake at hubs" tone="purple" />
        </div>
        <h2>Inclusive local sourcing</h2>
        <div className="grid g4">
          <Tile label="Order value" value={ksh(d.sourcing.po_value)} note={`${d.sourcing.orders} purchase orders`} />
          <Tile label="Smallholder suppliers" value={pct(d.sourcing.smallholder_share.pct)} note={`${ksh(d.sourcing.smallholder_share.value)} to farmers, groups & cooperatives`} tone="leaf" />
          <Tile label="Women/youth-led (verified)" value={pct(d.sourcing.inclusive_share.pct)} note={ksh(d.sourcing.inclusive_share.value)} tone="gold" />
          <Tile label="Suppliers from the same county" value={pct(d.sourcing.local_share.pct)} note={ksh(d.sourcing.local_share.value)} tone="purple" />
        </div>
        <div className="grid g3">
          <Tile label="Producers supplying hubs" value={d.sourcing.producers} />
          <Tile label="Women producers" value={pct(d.sourcing.women_producers_pct)} note="Where gender was recorded voluntarily" tone="leaf" />
          <Tile label="Youth producers" value={pct(d.sourcing.youth_producers_pct)} tone="gold" />
        </div>
        <h2>Finance & accountability</h2>
        <div className="grid g4">
          <Tile label="Paid to suppliers" value={ksh(d.finance.paid)} />
          <Tile label="Average days to pay" value={d.finance.avg_days_to_pay ?? "—"} note="Invoice submitted → paid" tone="leaf" />
          <Tile label="Invoices awaiting payment" value={d.finance.invoices_pending} note={ksh(d.finance.pending_value)} tone="gold" />
          <Tile label="Open exceptions" value={d.accountability.open_exceptions} note={`${d.accountability.overdue_exceptions} overdue · ${d.accountability.complaints} complaints · ${pct(d.accountability.complaints_resolved_in_sla_pct)} resolved on time`} tone="purple" />
        </div>
        <div className="row"><h2>Trends</h2><span className="spacer" /><button className="btn sm" onClick={() => setTable(!table)}>{table ? "Show charts" : "Show as table"}</button></div>
        {table ? <div className="card"><div className="tablewrap"><table><thead><tr><th>Month</th><th className="r">Accepted at schools</th><th className="r">Paid to suppliers</th></tr></thead>
          <tbody>{d.monthly.map((m) => <tr key={m.month}><td>{month(m.month)}</td><td className="r num">{kg(m.delivered_kg)}</td><td className="r num">{ksh(m.paid)}</td></tr>)}</tbody></table></div>
          <div className="tablewrap" style={{ marginTop: 12 }}><table><thead><tr><th>Commodity</th><th className="r">Accepted</th></tr></thead>
            <tbody>{d.food.by_commodity.map((c) => <tr key={c.commodity}><td>{c.commodity}</td><td className="r num">{kg(c.accepted_kg)}</td></tr>)}</tbody></table></div></div>
          : <div className="grid g3" style={{ alignItems: "start" }}>
            <div className="card"><h3>Food accepted at schools by month</h3><Bars vertical label="Kilograms accepted per month" data={d.monthly.map((m) => ({ k: month(m.month), v: Number(m.delivered_kg) }))} fmt={(n) => kg(n)} /></div>
            <div className="card"><h3>Paid to suppliers by month</h3><Bars vertical label="Shillings paid per month" data={d.monthly.map((m) => ({ k: month(m.month), v: Number(m.paid) }))} fmt={(n) => ksh(n)} /></div>
            <div className="card"><h3>Accepted by commodity</h3><Bars label="Kilograms accepted per commodity" data={d.food.by_commodity.map((c) => ({ k: c.commodity, v: Number(c.accepted_kg) }))} fmt={(n) => kg(n)} /></div>
          </div>}
        {!!exportsList.length && <div className="card"><h2>Download data</h2>
          <p className="small muted">Exports follow your area and are recorded in the audit trail. Producer data is aggregated by hub; no names or phone numbers are included.</p>
          <div className="tablewrap"><table><tbody>{exportsList.map((x) => <tr key={x.key}><td>{x.label}</td>
            <td className="r"><a className="btn sm" href={`/api/v1/meal/exports/${x.key}.xlsx${county ? `?county_id=${county}` : ""}`}>Excel</a>{" "}
              <a className="btn sm" href={`/api/v1/meal/exports/${x.key}.csv${county ? `?county_id=${county}` : ""}`}>CSV</a></td></tr>)}</tbody></table></div></div>}
      </div>}
    </>
  );
}
