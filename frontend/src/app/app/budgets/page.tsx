"use client";
import { useCallback, useEffect, useState } from "react";
import { WorkflowPanel, type WF } from "@/components/Workflow";
import { ErrorBox, Field, PageHead, Pill, useToast } from "@/components/ui";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate } from "@/lib/format";
import { ksh } from "@/lib/planning";

type Line = { id: string; code: string; name: string; funding_source: string; org: string; period_start: string; period_end: string;
  approved: number; committed: number; invoiced: number; paid: number; available: number; utilisation_pct: number; alerts: { code: string; message: string; severity: string }[] };
type Exc = { id: string; line: string; source_ref: string; requested_amount: number; shortfall: number; justification: string; status: string; decision_note: string; workflow: WF | null };
type Opt = { id: string; name: string };

export default function Budgets() {
  const { can } = useAuth();
  const [rows, setRows] = useState<Line[]>([]);
  const [exc, setExc] = useState<Exc[]>([]);
  const [fs, setFs] = useState<Opt[]>([]);
  const [counties, setCounties] = useState<Opt[]>([]);
  const [f, setF] = useState({ code: "", name: "", funding_source_id: "", org_id: "", period_start: "", period_end: "", approved_amount: "" });
  const [err, setErr] = useState<unknown>(null);
  const { toast, node } = useToast();
  const load = useCallback(() => { get<Line[]>("/budget-lines").then(setRows).catch(setErr); get<Exc[]>("/budget-exceptions").then(setExc).catch(() => {}); }, []);
  useEffect(() => { load(); get<Opt[]>("/funding-sources").then(setFs).catch(() => {}); get<Opt[]>("/public/counties").then(setCounties).catch(() => {}); }, [load]);
  const run = async (fn: () => Promise<unknown>, ok: string) => { setErr(null); try { await fn(); toast(ok); load(); } catch (e) { setErr(e); } };
  return (
    <>
      <PageHead crumb="Plan" title="Budgets & commitments" sub="Approved − committed − invoiced − paid = available. Plans cannot be approved beyond available budget without an exception." />
      <ErrorBox error={err} />
      <div className="card" style={{ marginBottom: 16 }}><div className="tablewrap"><table>
        <thead><tr><th>Budget line</th><th>Funding</th><th className="r">Approved</th><th className="r">Committed</th><th className="r">Paid</th><th className="r">Available</th><th>Utilisation</th></tr></thead>
        <tbody>{rows.map((l) => <tr key={l.id}><td><b>{l.name}</b><div className="small muted">{l.code} · {l.org} · {fmtDate(l.period_start)}–{fmtDate(l.period_end)}</div>
          {l.alerts.map((a) => <div key={a.code} className={`pill ${a.severity === "high" ? "p-red" : "p-amber"}`} style={{ marginTop: 4 }}>{a.message}</div>)}</td>
          <td className="small">{l.funding_source}</td><td className="r num">{ksh(l.approved)}</td><td className="r num">{ksh(l.committed)}</td><td className="r num">{ksh(l.paid)}</td>
          <td className="r num"><b style={{ color: l.available < 0 ? "var(--danger)" : undefined }}>{ksh(l.available)}</b></td>
          <td style={{ minWidth: 130 }}><div style={{ height: 8, background: "#EEF0E9", borderRadius: 6, overflow: "hidden" }}>
            <div style={{ width: `${Math.min(100, l.utilisation_pct)}%`, height: "100%", background: l.utilisation_pct >= 80 ? "var(--amber)" : "var(--green)" }} /></div>
            <span className="small muted">{l.utilisation_pct}%</span></td></tr>)}
          {!rows.length && <tr><td colSpan={7} className="muted">No budget lines yet.</td></tr>}</tbody></table></div></div>
      <div className="grid" style={{ gridTemplateColumns: can("bud:create") ? "2fr 1fr" : "1fr", alignItems: "start" }}>
        <div className="stack"><h2>Budget exceptions</h2>
          {exc.map((e) => <div key={e.id} className="card"><div className="row"><b>{e.source_ref}</b><span className="small muted">{e.line}</span><span className="spacer" /><Pill status={e.status === "pending" ? "in_review" : e.status} label={e.status} /></div>
            <p className="small" style={{ margin: "8px 0" }}>Shortfall <b>{ksh(e.shortfall)}</b> of {ksh(e.requested_amount)} — “{e.justification}”</p>
            {e.decision_note && <p className="small muted">Decision: {e.decision_note}</p>}
            <WorkflowPanel wf={e.workflow} onDone={load} /></div>)}
          {!exc.length && <div className="card muted">No exceptions.</div>}</div>
        {can("bud:create") && <div className="card"><h3>New budget line</h3>
          <Field label="Code"><input value={f.code} onChange={(e) => setF({ ...f, code: e.target.value })} placeholder="e.g. A-T1-2027" /></Field>
          <Field label="Name"><input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
          <Field label="Funding source"><select value={f.funding_source_id} onChange={(e) => setF({ ...f, funding_source_id: e.target.value })}><option value="">Choose…</option>{fs.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></Field>
          <Field label="County"><select value={f.org_id} onChange={(e) => setF({ ...f, org_id: e.target.value })}><option value="">Choose…</option>{counties.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></Field>
          <div className="grid g2"><Field label="From"><input type="date" value={f.period_start} onChange={(e) => setF({ ...f, period_start: e.target.value })} /></Field>
            <Field label="To"><input type="date" value={f.period_end} onChange={(e) => setF({ ...f, period_end: e.target.value })} /></Field></div>
          <Field label="Approved amount (KSh)"><input type="number" min={1} value={f.approved_amount} onChange={(e) => setF({ ...f, approved_amount: e.target.value })} /></Field>
          <button className="btn primary" disabled={!f.code || !f.funding_source_id || !f.org_id || !f.approved_amount}
            onClick={() => run(() => post("/budget-lines", f), "Budget line created")}>Create</button></div>}
      </div>
      {node}
    </>
  );
}
