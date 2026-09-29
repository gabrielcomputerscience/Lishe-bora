"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { ErrorBox, PageHead, Pill } from "@/components/ui";
import { get } from "@/lib/api";
import { fmtDate, human } from "@/lib/format";
import type { Paged, Supplier } from "@/lib/types";

const STATUSES = ["", "submitted", "under_review", "approved", "prequalified", "active", "suspended", "rejected"];

function Registry() {
  const qs = useSearchParams();
  const [status, setStatus] = useState(qs.get("status") ?? "");
  const [q, setQ] = useState("");
  const [data, setData] = useState<Paged<Supplier> | null>(null);
  const [err, setErr] = useState<unknown>(null);
  useEffect(() => {
    const t = setTimeout(() => {
      const p = new URLSearchParams({ size: "50" }); if (status) p.set("status", status); if (q) p.set("q", q);
      get<Paged<Supplier>>(`/suppliers?${p}`).then(setData).catch(setErr);
    }, 250);
    return () => clearTimeout(t);
  }, [status, q]);
  return (
    <>
      <PageHead crumb="Source › Supplier registry" title="Supplier registry & prequalification" sub="Verify documents and inclusion status, approve commodity categories" />
      <div className="card" style={{ marginBottom: 16 }}><div className="row">
        <input aria-label="Search" placeholder="Search name or phone" value={q} onChange={(e) => setQ(e.target.value)} className="btn" style={{ fontWeight: 400, minWidth: 240 }} />
        <select aria-label="Status" className="btn" value={status} onChange={(e) => setStatus(e.target.value)}>
          {STATUSES.map((s) => <option key={s} value={s}>{s ? human(s) : "All statuses"}</option>)}</select>
        <span className="spacer" /><span className="small muted">{data?.total ?? 0} suppliers in your area</span></div></div>
      <ErrorBox error={err} />
      <div className="card"><div className="tablewrap"><table>
        <thead><tr><th>Applicant</th><th>Type</th><th>County</th><th>Inclusion</th><th>Docs</th><th>Registered</th><th>Status</th><th /></tr></thead>
        <tbody>{data?.items.map((s) => (
          <tr key={s.id}><td><b>{s.legal_name}</b><div className="small muted">{s.phone}</div></td><td>{human(s.supplier_type)}</td><td>{s.county_name}</td>
            <td className="small">{s.inclusion_claim?.leadership && s.inclusion_claim.leadership !== "prefer_not_to_say" && s.inclusion_claim.leadership !== "none"
              ? `${human(String(s.inclusion_claim.leadership))}-led ${s.inclusion_verified ? "(verified)" : "(claimed)"}` : "—"}</td>
            <td>{s.documents.length}</td><td>{fmtDate(s.created_at)}</td><td><Pill status={s.status} /></td>
            <td className="r"><Link className="btn sm primary" href={`/app/suppliers/${s.id}`}>Open</Link></td></tr>))}
          {data && !data.items.length && <tr><td colSpan={8} className="muted">No suppliers match.</td></tr>}
        </tbody></table></div></div>
    </>
  );
}
export default function Page() { return <Suspense><Registry /></Suspense>; }
