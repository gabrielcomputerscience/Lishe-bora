"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { PageHead, Pill } from "@/components/ui";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Paged, Supplier } from "@/lib/types";
import { menuFor } from "@/lib/menu";

export default function Dashboard() {
  const { me, can } = useAuth();
  const [mine, setMine] = useState<Supplier | null>(null);
  const [inbox, setInbox] = useState<number | null>(null);
  const [reg, setReg] = useState<(Paged<Supplier> & { counts: Record<string, number> }) | null>(null);
  useEffect(() => {
    get<{ waiting_for_me: unknown[] }>("/workflow/inbox").then((d) => setInbox(d.waiting_for_me.length)).catch(() => {});
    if (me?.supplier_id) get<Supplier>("/suppliers/me").then(setMine).catch(() => {});
    if (me && menuFor(me, can).some((i) => i.href === "/app/suppliers")) get<Paged<Supplier> & { counts: Record<string, number> }>("/suppliers?size=5&status=submitted").then(setReg).catch(() => {});
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
      <div className="card"><h2>Your work</h2>
        <p className="small muted" style={{ marginTop: -4 }}>The parts of LisheBora used in your role.</p>
        <div className="grid g3" style={{ marginTop: 10 }}>
          {menuFor(me, can).filter((i) => i.hint && !["/app", "/app/notifications", "/app/profile"].includes(i.href)).map((i) => (
            <Link key={i.href} href={i.href} className="card" style={{ textDecoration: "none", color: "inherit", boxShadow: "none", border: "1px solid var(--line)" }}>
              <b style={{ color: "var(--green-900)" }}>{i.label}</b><div className="small muted">{i.hint}</div></Link>))}
        </div>
      </div>
    </>
  );
}
