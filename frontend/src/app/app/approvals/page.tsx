"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ErrorBox, PageHead, Pill } from "@/components/ui";
import type { WF } from "@/components/Workflow";
import { get } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";

export default function Approvals() {
  const [d, setD] = useState<{ waiting_for_me: WF[]; submitted_by_me: WF[] } | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const load = useCallback(() => get<{ waiting_for_me: WF[]; submitted_by_me: WF[] }>("/workflow/inbox").then(setD).catch(setErr), []);
  useEffect(() => { load(); }, [load]);
  const table = (rows: WF[], empty: string) => (
    <div className="card"><div className="tablewrap"><table>
      <thead><tr><th>Item</th><th>Type</th><th>Step</th><th>Submitted</th><th>Due</th><th /></tr></thead>
      <tbody>{rows.map((w) => <tr key={w.id}><td><b>{w.title}</b><div className="small muted">{w.entity_ref}</div></td><td>{w.name}</td>
        <td>{w.current_stage}</td><td className="small">{fmtDateTime(w.started_at)}</td>
        <td>{w.overdue ? <Pill status="rejected" label="Overdue" /> : <span className="small">{fmtDateTime(w.due_at)}</span>}</td>
        <td className="r">{w.link && <Link className="btn sm primary" href={w.link}>Open</Link>}</td></tr>)}
        {!rows.length && <tr><td colSpan={6} className="muted">{empty}</td></tr>}</tbody></table></div></div>);
  return (
    <>
      <PageHead crumb="Overview" title="My approvals" sub="Items waiting for your decision, and items you submitted." />
      <ErrorBox error={err} />
      <h2 style={{ margin: "8px 0 10px" }}>Waiting for me {d ? `(${d.waiting_for_me.length})` : ""}</h2>
      {d && table(d.waiting_for_me, "Nothing is waiting for you.")}
      <h2 style={{ margin: "24px 0 10px" }}>Submitted by me</h2>
      {d && table(d.submitted_by_me, "You have nothing in approval.")}
    </>
  );
}
