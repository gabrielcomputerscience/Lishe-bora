"use client";
import { useEffect, useState } from "react";
import { ErrorBox, PageHead } from "@/components/ui";
import { get } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";

type Row = { id: string; at: string; user: string; roles: string; action: string; entity: string; entity_id: string; before: unknown; after: unknown; reason: string };
export default function Audit() {
  const [rows, setRows] = useState<Row[]>([]);
  const [total, setTotal] = useState(0);
  const [entity, setEntity] = useState("");
  const [page, setPage] = useState(1);
  const [err, setErr] = useState<unknown>(null);
  useEffect(() => {
    get<{ total: number; items: Row[] }>(`/audit?page=${page}&size=50${entity ? `&entity=${entity}` : ""}`).then((d) => { setRows(d.items); setTotal(d.total); }).catch(setErr);
  }, [entity, page]);
  return (
    <>
      <PageHead crumb="Oversight › Audit trail" title="Audit trail" sub="Append-only record of every material action. Read-only.">
        <select className="btn" value={entity} onChange={(e) => { setEntity(e.target.value); setPage(1); }}>
          {["", "user", "supplier", "supplier_document", "cms_news", "cms_page", "cms_block", "commodity", "organization", "procurement_event"].map((x) => <option key={x} value={x}>{x || "All records"}</option>)}</select>
      </PageHead>
      <ErrorBox error={err} />
      <div className="card"><div className="tablewrap"><table><thead><tr><th>When (EAT)</th><th>User</th><th>Action</th><th>Record</th><th>Change</th></tr></thead>
        <tbody>{rows.map((r) => <tr key={r.id}><td className="small num">{fmtDateTime(r.at)}</td><td className="small">{r.user}<div className="muted">{r.roles}</div></td>
          <td><span className="pill p-grey">{r.action}</span></td><td className="small"><b>{r.entity}</b><div className="muted">{r.entity_id.slice(0, 8)}</div></td>
          <td className="small" style={{ maxWidth: 380 }}>{r.before ? <div className="muted">before: {JSON.stringify(r.before)}</div> : null}{r.after ? <div>after: {JSON.stringify(r.after)}</div> : null}{r.reason && <div>reason: {r.reason}</div>}</td></tr>)}</tbody></table></div></div>
      <div className="row" style={{ marginTop: 12 }}><button className="btn sm" disabled={page === 1} onClick={() => setPage(page - 1)}>← Newer</button>
        <span className="small muted">Page {page} of {Math.max(1, Math.ceil(total / 50))}</span>
        <button className="btn sm" disabled={page * 50 >= total} onClick={() => setPage(page + 1)}>Older →</button></div>
    </>
  );
}
