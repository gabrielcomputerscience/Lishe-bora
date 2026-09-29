"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { PageHead, Pill } from "@/components/ui";
import { get } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { countdown } from "@/lib/procurement";

type O = { id: string; reference: string; title: string; county: string; closes_at: string; status: string; lot_count: number; eligible: boolean; why_not: string[]; my_bid: string | null };
export default function Opportunities() {
  const [rows, setRows] = useState<O[]>([]);
  useEffect(() => { get<O[]>("/supplier/opportunities").then(setRows).catch(() => {}); }, []);
  return (
    <>
      <PageHead crumb="Supplier" title="Opportunities" sub="Open sourcing events you can bid on, and events you have bid on." />
      <div className="stack">{rows.map((o) => (
        <div key={o.id} className="card"><div className="row">
          <div><b>{o.reference}</b> · {o.title}<div className="small muted">{o.county} · {o.lot_count} lots · closes {fmtDateTime(o.closes_at)}{o.status === "open" ? ` (${countdown(o.closes_at)})` : ""}</div>
            {!o.eligible && o.status === "open" && <div className="small" style={{ color: "var(--gold-700)" }}>{o.why_not.join(" ")}</div>}</div>
          <span className="spacer" /><Pill status={o.status} />{o.my_bid && <Pill status={o.my_bid} label={`My bid: ${o.my_bid}`} />}
          <Link className="btn sm primary" href={`/app/opportunities/${o.id}`}>{o.status === "open" && o.eligible ? (o.my_bid ? "View / revise bid" : "Prepare bid") : "View"}</Link></div></div>))}
        {!rows.length && <div className="card muted">No open opportunities right now. You will get an SMS when one matching your categories is published.</div>}</div>
    </>
  );
}
