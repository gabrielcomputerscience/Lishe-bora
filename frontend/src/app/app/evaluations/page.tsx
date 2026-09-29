"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { PageHead, Pill } from "@/components/ui";
import { get } from "@/lib/api";

type A = { event_id: string; reference: string; title: string; status: string; coi_declared: boolean; has_conflict: boolean; submitted: boolean };
export default function Evaluations() {
  const [rows, setRows] = useState<A[]>([]);
  useEffect(() => { get<A[]>("/evaluations").then(setRows).catch(() => {}); }, []);
  return (
    <>
      <PageHead crumb="Source" title="My evaluations" sub="Declare any conflict of interest first. Bids are shown only after that." />
      <div className="card"><div className="tablewrap"><table><thead><tr><th>Event</th><th>Event status</th><th>My declaration</th><th>My scores</th><th /></tr></thead>
        <tbody>{rows.map((a) => <tr key={a.event_id}><td><b>{a.reference}</b><div className="small muted">{a.title}</div></td><td><Pill status={a.status} /></td>
          <td>{!a.coi_declared ? <Pill status="draft" label="Needed" /> : a.has_conflict ? <Pill status="rejected" label="Conflict declared" /> : <Pill status="verified" label="No conflict" />}</td>
          <td>{a.submitted ? <Pill status="approved" label="Submitted" /> : <Pill status="draft" label="Pending" />}</td>
          <td className="r"><Link className="btn sm primary" href={`/app/evaluations/${a.event_id}`}>Open</Link></td></tr>)}
          {!rows.length && <tr><td colSpan={5} className="muted">You have not been assigned to any evaluation.</td></tr>}</tbody></table></div></div>
    </>
  );
}
