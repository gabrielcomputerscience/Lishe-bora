"use client";
import { useCallback, useEffect, useState } from "react";
import { ErrorBox, Field, PageHead, Pill, useToast } from "@/components/ui";
import { ApiError, get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Complaint } from "@/lib/finance";
import { fmtDateTime, human } from "@/lib/format";

const ACTION_LABEL: Record<string, string> = { comment: "Add comment", investigate: "Start / update investigation", respond: "Respond as supplier",
  resolve: "Resolve", confirm: "Confirm resolved", reopen: "Not resolved, reopen" };

export default function Complaints() {
  const { can } = useAuth();
  const [rows, setRows] = useState<Complaint[]>([]);
  const [cats, setCats] = useState<{ key: string; label: string }[]>([]);
  const [sups, setSups] = useState<{ id: string; name: string }[]>([]);
  const [filter, setFilter] = useState("submitted,investigating,resolved");
  const [sel, setSel] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [f, setF] = useState({ category: "food_quality", subject: "", description: "", priority: "medium", supplier_id: "", entity_ref: "", anonymous: false });
  const [note, setNote] = useState(""); const [sat, setSat] = useState(0);
  const [fe, setFe] = useState<Record<string, string>>({});
  const [err, setErr] = useState<unknown>(null);
  const { toast, node } = useToast();
  const load = useCallback(() => { get<Complaint[]>(`/complaints${filter ? `?status=${filter}` : ""}`).then(setRows).catch(setErr); }, [filter]);
  useEffect(() => {
    load(); get<typeof cats>("/complaints/categories").then(setCats).catch(() => {});
    if (can("cmp:create")) get<typeof sups>("/complaints/suppliers").then(setSups).catch(() => {});
    setSel(new URLSearchParams(window.location.search).get("id"));
  }, [load, can]);
  const c = rows.find((x) => x.id === sel) ?? null;
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setErr(null); setFe({});
    try { const r = await post<Complaint>("/complaints", { ...f, supplier_id: f.supplier_id || null }); toast(`Complaint ${r.reference} submitted`); setShowNew(false); setSel(r.id);
      setF({ ...f, subject: "", description: "", entity_ref: "" }); load(); }
    catch (x) { if (x instanceof ApiError) setFe(x.fieldErrors()); setErr(x); }
  }
  async function act(action: string) {
    if (!c) return; setErr(null);
    try { await post(`/complaints/${c.id}/actions`, { action, note, satisfaction: action === "confirm" ? sat || null : null }); setNote(""); toast("Saved"); load(); }
    catch (x) { setErr(x); }
  }
  return (
    <>
      <PageHead crumb="Performance" title="Complaints & grievances" sub="Raised by schools, suppliers, staff or the public. Each case has a due date; the person who raised it confirms the resolution.">
        <select className="btn" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Status"><option value="submitted,investigating,resolved">Open</option>
          <option value="closed">Closed</option><option value="">All</option></select>
        {can("cmp:create") && <button className="btn primary" onClick={() => setShowNew(!showNew)}>Raise a complaint</button>}
      </PageHead>
      <ErrorBox error={err} />
      {showNew && <form className="card" style={{ marginBottom: 16 }} onSubmit={submit}>
        <h2>Raise a complaint</h2>
        <div className="grid g3">
          <Field label="Category"><select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>{cats.map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}</select></Field>
          <Field label="Priority" hint="Safeguarding and fraud are always high"><select value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })}>
            <option value="high">High (3 days)</option><option value="medium">Medium (7 days)</option><option value="low">Low (14 days)</option></select></Field>
          <Field label="About which supplier (optional)"><select value={f.supplier_id} onChange={(e) => setF({ ...f, supplier_id: e.target.value })}><option value="">Not about a supplier</option>
            {sups.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></Field>
        </div>
        <Field label="Subject" error={fe.subject}><input value={f.subject} onChange={(e) => setF({ ...f, subject: e.target.value })} /></Field>
        <Field label="What happened?" error={fe.description}><textarea rows={4} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
        <div className="grid g2">
          <Field label="Related reference (optional)" hint="e.g. a dispatch or order number"><input value={f.entity_ref} onChange={(e) => setF({ ...f, entity_ref: e.target.value })} /></Field>
          <label className="chk" style={{ alignSelf: "end" }}><input type="checkbox" checked={f.anonymous} onChange={(e) => setF({ ...f, anonymous: e.target.checked })} /> Hide my name from the supplier and in reports</label>
        </div>
        <button className="btn primary" type="submit">Submit</button>
      </form>}
      <div className="grid g2" style={{ alignItems: "start" }}>
        <div className="card"><div className="tablewrap"><table><tbody>{rows.map((x) => <tr key={x.id} style={{ background: x.id === sel ? "#F4F7EE" : undefined }}>
          <td><b>{x.reference}</b> <Pill status={x.priority} label={human(x.priority)} /><div className="small">{x.subject}</div>
            <div className="small muted">{x.category_label}{x.school ? ` · ${x.school}` : ""}{x.supplier ? ` · ${x.supplier}` : ""} · {x.channel}</div></td>
          <td>{x.overdue && <Pill status="rejected" label="Overdue" />}<Pill status={x.status} /></td>
          <td className="r"><button className="btn sm" onClick={() => setSel(x.id)}>Open</button></td></tr>)}
          {!rows.length && <tr><td className="muted">No complaints.</td></tr>}</tbody></table></div></div>
        {c && <div className="card">
          <div className="row"><h2>{c.reference}</h2><Pill status={c.status} /><span className="spacer" /><span className="small muted">due {fmtDateTime(c.due_at)}</span></div>
          <h3 style={{ marginTop: 6 }}>{c.subject}</h3>
          <p>{c.description}</p>
          <p className="small muted">{c.category_label} · {human(c.priority)} priority · raised by {c.submitted_by}{c.contact ? ` (${c.contact})` : ""} via {c.channel} · {fmtDateTime(c.created_at)}
            {c.county ? ` · ${c.county}` : ""}{c.school ? ` · ${c.school}` : ""}{c.supplier ? ` · about ${c.supplier}` : ""}{c.entity_ref ? ` · ref ${c.entity_ref}` : ""}{c.assigned_to ? ` · handled by ${c.assigned_to}` : ""}</p>
          {c.resolution && <div className="alert info small">Resolution: {c.resolution}{c.satisfaction ? ` · satisfaction ${c.satisfaction}/5` : ""}</div>}
          <h3>History</h3>
          <div className="small">{c.history.map((hh, i) => <div key={i} style={{ padding: "5px 0", borderTop: "1px solid var(--line)" }}><b>{human(hh.action)}</b> · {hh.by} · <span className="muted">{fmtDateTime(hh.at)}</span>{hh.note && <div className="muted">{hh.note}</div>}</div>)}</div>
          {!!c.actions?.length && <div style={{ marginTop: 12 }}>
            <Field label="Note"><textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
            {c.actions.includes("confirm") && <Field label="How satisfied are you with the resolution?"><select value={sat} onChange={(e) => setSat(Number(e.target.value))}>
              <option value={0}>Choose…</option>{[5, 4, 3, 2, 1].map((n) => <option key={n} value={n}>{n} · {["", "Very unsatisfied", "Unsatisfied", "Neutral", "Satisfied", "Very satisfied"][n]}</option>)}</select></Field>}
            <div className="row">{c.actions.map((a) => <button key={a} className={`btn sm ${a === "resolve" || a === "confirm" ? "primary" : ""}`} onClick={() => act(a)}>{ACTION_LABEL[a] ?? a}</button>)}</div>
          </div>}
        </div>}
      </div>
      {node}
    </>
  );
}
