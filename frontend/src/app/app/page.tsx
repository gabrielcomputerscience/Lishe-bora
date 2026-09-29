"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { PageHead, Pill } from "@/components/ui";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Paged, Supplier } from "@/lib/types";

const ROADMAP = [
  ["Phase 1 · Platform foundation", "Sign-in, roles and data scope, supplier registry, documents, audit trail, public website", "now"],
  ["Phase 2 · Demand & budget", "School demand, menus, stock, consolidation, procurement plans, budget controls, approval engine", "now"],
  ["Phase 3 · e-Procurement", "RFQs, sealed bids, evaluation, approvals, awards, POs, contracts", "now"],
  ["Phase 4 · Supply-chain fulfilment", "Aggregation, quality, inventory, dispatch, e-proof of delivery (offline), exceptions, traceability", "now"],
  ["Phase 5 · Finance & performance", "Three-way match, payments, complaints, supplier scorecards, MEAL dashboards and exports", "now"],
  ["Phase 6 · Advanced & integrations", "Installable offline app, QR labels & recall, GIS map & routes, forecasting & price intelligence, risk flags, payment files, statement reconciliation, IFMIS export", "now"],
  ["Phase 7 · Pilot readiness", "PostgreSQL-verified, SMS/email outbox (Africa's Talking, SMTP), background worker & reminders, CSRF and rate limits, school/staff CSV import, Docker + HTTPS deployment, backups", "now"],
];

export default function Dashboard() {
  const { me, can } = useAuth();
  const [mine, setMine] = useState<Supplier | null>(null);
  const [inbox, setInbox] = useState<number | null>(null);
  const [reg, setReg] = useState<(Paged<Supplier> & { counts: Record<string, number> }) | null>(null);
  useEffect(() => {
    get<{ waiting_for_me: unknown[] }>("/workflow/inbox").then((d) => setInbox(d.waiting_for_me.length)).catch(() => {});
    if (me?.supplier_id) get<Supplier>("/suppliers/me").then(setMine).catch(() => {});
    if (can("sup:view")) get<Paged<Supplier> & { counts: Record<string, number> }>("/suppliers?size=5&status=submitted").then(setReg).catch(() => {});
  }, [me, can]);
  if (!me) return null;
  return (
    <>
      <PageHead crumb="Dashboard" title={`Welcome, ${me.full_name.split(" ")[0]}`} sub={me.roles.map((r) => r.role_name + (r.org_name ? ` · ${r.org_name}` : "")).join(" | ")} />
      {!!inbox && <div className="alert warn" style={{ marginBottom: 16 }}><b>{inbox}</b> item{inbox > 1 ? "s" : ""} waiting for your approval. <Link href="/app/approvals">Open approvals →</Link></div>}
      {mine && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="row"><h2>{mine.legal_name}</h2><Pill status={mine.status} /></div>
          <div className="steps" style={{ marginTop: 14 }}>{["submitted", "under_review", "approved", "prequalified", "active"].map((s, i, arr) => {
            const cur = arr.indexOf(mine.status);
            return <div key={s} className={`step ${i < cur ? "done" : ""} ${i === cur ? "cur" : ""}`}>{s.replace("_", " ")}</div>;
          })}</div>
          {mine.status === "submitted" && <div className="alert warn">Upload your registration certificate and payment details so the county can review your application. <Link href="/app/my-supplier">Go to documents →</Link></div>}
          {mine.status_note && <div className="alert info">Note from reviewer: {mine.status_note}</div>}
        </div>)}
      {reg && (
        <div className="grid g4" style={{ marginBottom: 16 }}>
          <div className="card kpi"><div className="l">New applications</div><div className="v">{reg.total}</div></div>
          <div className="card kpi gold"><div className="l">Under review</div><div className="v">{reg.counts.under_review ?? "—"}</div></div>
          <div className="card kpi leaf"><div className="l">Prequalified</div><div className="v">{reg.counts.prequalified ?? "—"}</div></div>
          <div className="card kpi purple"><div className="l">Rejected</div><div className="v">{reg.counts.rejected ?? "—"}</div></div>
        </div>)}
      {reg && reg.items.length > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="row" style={{ marginBottom: 10 }}><h2>Applications waiting for review</h2><span className="spacer" /><Link href="/app/suppliers?status=submitted">All →</Link></div>
          <div className="tablewrap"><table><thead><tr><th>Applicant</th><th>Type</th><th>County</th><th>Docs</th><th /></tr></thead>
            <tbody>{reg.items.map((s) => <tr key={s.id}><td><b>{s.legal_name}</b></td><td>{s.supplier_type}</td><td>{s.county_name}</td><td>{s.documents.length}</td>
              <td className="r"><Link className="btn sm primary" href={`/app/suppliers/${s.id}`}>Review</Link></td></tr>)}</tbody></table></div>
        </div>)}
      <div className="card"><h2>Build roadmap</h2>
        {ROADMAP.map(([t, d, s]) => <div key={t} className="row" style={{ padding: "10px 0", borderBottom: "1px solid var(--line)" }}>
          <div><b>{t}</b><div className="small muted">{d}</div></div><span className="spacer" />
          <Pill status={s === "now" ? "active" : "draft"} label={s === "now" ? "In this build" : "Planned"} /></div>)}
      </div>
    </>
  );
}
