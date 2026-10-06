"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ErrorBox, PageHead, Pill, useToast } from "@/components/ui";
import { post, get } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { inMenu } from "@/lib/menu";
import { fmtDateTime, human } from "@/lib/format";
import type { Case } from "@/lib/fulfilment";

const LINK: Record<string, (c: Case) => string> = {
  batch: (c) => `/app/trace/${c.entity_ref}`, dispatch: (c) => `/app/deliveries?dispatch=${c.entity_id}`, stock_count: () => "/app/inventory",
};

export default function Exceptions() {
  const { me, can } = useAuth();
  const [rows, setRows] = useState<Case[]>([]);
  const [filter, setFilter] = useState("open,in_progress");
  const [text, setText] = useState<Record<string, string>>({});
  const [err, setErr] = useState<unknown>(null);
  const { toast, node } = useToast();
  const load = useCallback(() => { get<Case[]>(`/exceptions${filter ? `?status=${filter}` : ""}`).then(setRows).catch(setErr); }, [filter]);
  useEffect(() => { load(); }, [load]);
  async function act(c: Case, what: "progress" | "resolve") {
    setErr(null);
    try { await post(`/exceptions/${c.id}/${what}`, { text: text[c.id] ?? "" }); toast(what === "resolve" ? "Resolved" : "Corrective action recorded"); setText({ ...text, [c.id]: "" }); load(); }
    catch (x) { setErr(x); }
  }
  return (
    <>
      <PageHead crumb="Oversight" title="Exceptions" sub="Raised automatically for quality rejections, short, damaged, rejected or late deliveries, and large stock-count differences.">
        <select className="btn" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Status">
          <option value="open,in_progress">Open</option><option value="resolved,closed">Resolved</option><option value="">All</option></select></PageHead>
      <ErrorBox error={err} />
      <div className="stack">{rows.map((c) => <div key={c.id} className="card">
        <div className="row"><b>{c.reference}</b><Pill status={c.severity} label={`${human(c.severity)} severity`} /><span>{c.title}</span><span className="spacer" />
          {c.overdue && <Pill status="rejected" label="Overdue" />}<Pill status={c.status} /></div>
        <p className="small" style={{ margin: "6px 0" }}>{c.detail}</p>
        <p className="small muted">{human(c.category)} · {c.org ?? ""}{c.supplier ? ` · ${c.supplier}` : ""} · owner {human(c.owner_role)} · raised {fmtDateTime(c.created_at)} · due {fmtDateTime(c.due_at)}
          {LINK[c.entity] && (inMenu(me, can, LINK[c.entity](c)) ? <> · <Link href={LINK[c.entity](c)}>{c.entity_ref}</Link></> : <> · {c.entity_ref}</>)}</p>
        {c.corrective_action && <div className="alert info small">Corrective action: {c.corrective_action}</div>}
        {c.resolution && <div className="alert info small">Resolution: {c.resolution} · {c.resolved_by} · {fmtDateTime(c.resolved_at)}</div>}
        {(c.status === "open" || c.status === "in_progress") && (can("rsk:create", "rsk:edit", "rsk:approve")) && <div className="row" style={{ marginTop: 8 }}>
          <input className="btn" style={{ flex: 1, fontWeight: 400, minWidth: 220 }} placeholder="Corrective action or resolution…" aria-label={`Note ${c.reference}`} value={text[c.id] ?? ""} onChange={(e) => setText({ ...text, [c.id]: e.target.value })} />
          {can("rsk:create", "rsk:edit") && <button className="btn sm" onClick={() => act(c, "progress")}>Record action</button>}
          {can("rsk:approve", "rsk:edit") && <button className="btn sm primary" onClick={() => act(c, "resolve")}>Resolve</button>}</div>}
      </div>)}{!rows.length && <div className="card muted">No exceptions.</div>}</div>
      {node}
    </>
  );
}
