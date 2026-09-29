"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ErrorBox, Field, PageHead, Pill } from "@/components/ui";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime } from "@/lib/format";
import { ksh } from "@/lib/planning";
import { countdown, type Event } from "@/lib/procurement";

type Plan = { id: string; reference: string; title: string; status: string; estimated_value: number };
export default function Sourcing() {
  const { can } = useAuth();
  const router = useRouter();
  const [rows, setRows] = useState<Event[]>([]);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [f, setF] = useState({ plan_id: "", closes_at: "", method: "" });
  const [err, setErr] = useState<unknown>(null);
  useEffect(() => {
    get<Event[]>("/procurement-events").then(setRows).catch(setErr);
    if (can("src:create")) get<Plan[]>("/plans").then((p) => setPlans(p.filter((x) => x.status === "approved"))).catch(() => {});
  }, [can]);
  async function create(e: React.FormEvent) {
    e.preventDefault(); setErr(null);
    try { const ev = await post<Event>("/procurement-events/from-plan", { plan_id: f.plan_id, closes_at: new Date(f.closes_at).toISOString(), method: f.method || null });
      router.push(`/app/sourcing/${ev.id}`); } catch (x) { setErr(x); }
  }
  return (
    <>
      <PageHead crumb="Source" title="Sourcing events" sub="Approved plans become RFQs, tenders or frameworks. Bids stay sealed until formal opening after the deadline." />
      <ErrorBox error={err} />
      <div className="grid" style={{ gridTemplateColumns: can("src:create") ? "2fr 1fr" : "1fr", alignItems: "start" }}>
        <div className="card"><div className="tablewrap"><table>
          <thead><tr><th>Reference</th><th>Title</th><th>Method</th><th>Closes</th><th className="r">Bids</th><th>Status</th><th /></tr></thead>
          <tbody>{rows.map((e) => <tr key={e.id}><td><b>{e.reference}</b></td><td>{e.title}<div className="small muted">{e.lot_count} lots · {e.eligibility}</div></td>
            <td>{e.method.toUpperCase()}</td><td className="small">{fmtDateTime(e.closes_at)}{e.status === "open" && <div className="muted">{countdown(e.closes_at)}</div>}</td>
            <td className="r">{e.bids_received}</td><td><Pill status={e.status} /></td>
            <td className="r"><Link className="btn sm primary" href={`/app/sourcing/${e.id}`}>Open</Link></td></tr>)}
            {!rows.length && <tr><td colSpan={7} className="muted">No sourcing events yet.</td></tr>}</tbody></table></div></div>
        {can("src:create") && <form className="card" onSubmit={create}><h3>New event from an approved plan</h3>
          <Field label="Approved procurement plan"><select value={f.plan_id} onChange={(e) => setF({ ...f, plan_id: e.target.value })}><option value="">Choose…</option>
            {plans.map((p) => <option key={p.id} value={p.id}>{p.reference} · {ksh(p.estimated_value)}</option>)}</select></Field>
          <Field label="Method"><select value={f.method} onChange={(e) => setF({ ...f, method: e.target.value })}><option value="">As in plan</option><option value="rfq">RFQ</option><option value="competitive">Competitive tender</option><option value="framework">Framework agreement</option></select></Field>
          <Field label="Bids close at" hint="At least one hour from now. Clarifications close 2 days earlier."><input type="datetime-local" value={f.closes_at} onChange={(e) => setF({ ...f, closes_at: e.target.value })} /></Field>
          <button className="btn primary" disabled={!f.plan_id || !f.closes_at}>Create draft event</button>
          {!plans.length && <p className="small muted">No approved plans are waiting for sourcing.</p>}</form>}
      </div>
    </>
  );
}
