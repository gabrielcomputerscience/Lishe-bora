"use client";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ErrorBox, Field, PageHead, Pill, useToast } from "@/components/ui";
import { get, post, put } from "@/lib/api";
import { fmtDateTime, human } from "@/lib/format";
import { kg, ksh } from "@/lib/planning";
import { countdown, type Event } from "@/lib/procurement";

type MyBid = { id: string; status: string; revision: number; submitted_at: string | null; receipt: string | null;
  contents: { lines: { lot_id: string; unit_price: string; quantity: string; notes: string }[]; delivery_plan: string; technical_notes: string } | null };
type Opp = Event & { eligible: boolean; why_not: string[]; clarifications: { id: string; kind: string; question: string; answer: string; mine: boolean }[]; my_bid: MyBid | null };

export default function Opportunity() {
  const { id } = useParams<{ id: string }>();
  const [o, setO] = useState<Opp | null>(null);
  const [lines, setLines] = useState<Record<string, { unit_price: string; quantity: string; notes: string; on: boolean }>>({});
  const [plan, setPlan] = useState({ delivery_plan: "", technical_notes: "" });
  const [q, setQ] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const { toast, node } = useToast();
  const load = useCallback(() => get<Opp>(`/supplier/opportunities/${id}`).then((x) => {
    setO(x);
    const mine = Object.fromEntries((x.my_bid?.contents?.lines ?? []).map((l) => [l.lot_id, l]));
    setLines(Object.fromEntries(x.lots.map((l) => [l.id, { unit_price: mine[l.id]?.unit_price ?? "", quantity: mine[l.id]?.quantity ?? String(l.quantity), notes: mine[l.id]?.notes ?? "", on: !!mine[l.id] || !x.my_bid }])));
    setPlan({ delivery_plan: x.my_bid?.contents?.delivery_plan ?? "", technical_notes: x.my_bid?.contents?.technical_notes ?? "" });
  }).catch(setErr), [id]);
  useEffect(() => { load(); }, [load]);
  const run = async (fn: () => Promise<unknown>, ok: string) => { setErr(null); try { await fn(); toast(ok); await load(); } catch (x) { setErr(x); } };
  if (!o) return <ErrorBox error={err} />;
  const open = o.status === "open";
  const editable = open && o.eligible && (!o.my_bid || ["draft", "submitted", "withdrawn"].includes(o.my_bid.status));
  const body = () => ({ lines: o.lots.filter((l) => lines[l.id]?.on && lines[l.id]?.unit_price).map((l) => ({ lot_id: l.id, unit_price: lines[l.id].unit_price, quantity: lines[l.id].quantity, notes: lines[l.id].notes })), ...plan });
  const total = o.lots.reduce((s, l) => s + (lines[l.id]?.on ? Number(lines[l.id].unit_price || 0) * Number(l.quantity) : 0), 0);

  return (
    <>
      <PageHead crumb="Supplier › Opportunities" title={o.reference} sub={`${o.title} · ${o.county ?? ""}`}><Pill status={o.status} /></PageHead>
      <ErrorBox error={err} />
      <div className="grid g3" style={{ marginBottom: 16 }}>
        <div className="card kpi"><div className="l">Closes</div><div className="v" style={{ fontSize: 18 }}>{fmtDateTime(o.closes_at)}</div><div className="small muted">{open ? countdown(o.closes_at) : "Bidding closed"}</div></div>
        <div className="card kpi gold"><div className="l">Evaluation</div><div className="v" style={{ fontSize: 18 }}>Technical {o.technical_weight} · Price {o.financial_weight}</div></div>
        <div className="card kpi leaf"><div className="l">My bid</div><div className="v" style={{ fontSize: 18 }}>{o.my_bid ? human(o.my_bid.status) : "Not started"}</div>
          {o.my_bid?.receipt && <div className="small muted">Receipt {o.my_bid.receipt}</div>}</div>
      </div>
      {!o.eligible && open && <div className="alert warn">{o.why_not.join(" ")}</div>}
      {o.my_bid?.status === "awarded" && <div className="alert info"><b>Congratulations, you have been awarded.</b> See My contracts &amp; orders.</div>}
      {o.my_bid?.status === "unsuccessful" && <div className="alert warn">Your bid was not successful this time. You can ask for a clarification below.</div>}
      <div className="grid" style={{ gridTemplateColumns: "2fr 1fr", alignItems: "start" }}>
        <div className="card"><h3>{editable ? "Your prices" : "Lots"}</h3>
          <p className="small muted">Your bid is encrypted as soon as you save it. Nobody, including administrators, can read it before the deadline. You can revise it until then.</p>
          <div className="tablewrap"><table><thead><tr>{editable && <th>Bid</th>}<th>Lot</th><th className="r">Required</th><th className="r">Unit price (KSh)</th><th className="r">Qty offered</th></tr></thead>
            <tbody>{o.lots.map((l) => <tr key={l.id}>
              {editable && <td><input type="checkbox" aria-label={`Bid on lot ${l.lot_no}`} checked={lines[l.id]?.on ?? false} onChange={(x) => setLines({ ...lines, [l.id]: { ...lines[l.id], on: x.target.checked } })} /></td>}
              <td><b>{l.commodity}</b> <span className="small muted">lot {l.lot_no}</span><div className="small muted">{l.specification}</div><div className="small muted">Deliver to: {l.schools.map((s) => s.name).join(", ")}</div></td>
              <td className="r num">{kg(l.quantity, l.unit)}</td>
              <td className="r">{editable ? <input aria-label={`Price lot ${l.lot_no}`} type="number" min={0} step="0.01" className="btn" style={{ width: 110, fontWeight: 400, textAlign: "right" }}
                disabled={!lines[l.id]?.on} value={lines[l.id]?.unit_price ?? ""} onChange={(x) => setLines({ ...lines, [l.id]: { ...lines[l.id], unit_price: x.target.value } })} /> : (lines[l.id]?.unit_price || "—")}</td>
              <td className="r">{editable ? <input aria-label={`Quantity lot ${l.lot_no}`} type="number" min={0} className="btn" style={{ width: 100, fontWeight: 400, textAlign: "right" }}
                disabled={!lines[l.id]?.on} value={lines[l.id]?.quantity ?? ""} onChange={(x) => setLines({ ...lines, [l.id]: { ...lines[l.id], quantity: x.target.value } })} /> : (lines[l.id]?.quantity || "—")}</td></tr>)}</tbody></table></div>
          <p className="small">Bid total: <b>{ksh(total)}</b> · Offering less than the required quantity makes a lot non-responsive.</p>
          {editable && <><Field label="Delivery plan"><textarea rows={2} value={plan.delivery_plan} onChange={(x) => setPlan({ ...plan, delivery_plan: x.target.value })} placeholder="e.g. two deliveries per month by our own lorry" /></Field>
            <Field label="Technical information" hint="Capacity, storage, quality controls, certifications"><textarea rows={3} value={plan.technical_notes} onChange={(x) => setPlan({ ...plan, technical_notes: x.target.value })} /></Field>
            <div className="row" style={{ justifyContent: "flex-end" }}>
              {o.my_bid && ["draft", "submitted"].includes(o.my_bid.status) && <button className="btn danger" onClick={() => run(() => post(`/supplier/opportunities/${id}/bid/withdraw`), "Bid withdrawn")}>Withdraw</button>}
              <button className="btn" onClick={() => run(() => put(`/supplier/opportunities/${id}/bid`, body()), "Draft saved (sealed)")}>Save draft</button>
              <button className="btn primary" onClick={() => run(async () => { await put(`/supplier/opportunities/${id}/bid`, body()); await post(`/supplier/opportunities/${id}/bid/submit`); }, "Bid submitted")}>Submit bid</button></div>
            {o.my_bid?.status === "draft" && <div className="alert warn small">Your latest changes are saved but <b>not submitted</b>. Click Submit bid before the deadline.</div>}</>}
        </div>
        <div className="card"><h3>Questions &amp; answers</h3>
          {o.clarifications.map((c) => <div key={c.id} style={{ borderTop: "1px solid var(--line)", padding: "8px 0" }}>
            <div className="small"><b>{c.kind === "amendment" ? "Amendment: " : "Q: "}</b>{c.question}{c.mine && <span className="muted"> (yours)</span>}</div>
            <div className="small muted">{c.answer || "Awaiting answer"}</div></div>)}
          {!o.clarifications.length && <p className="small muted">No questions yet.</p>}
          {(open || o.status === "awarded") && <><Field label={o.status === "awarded" ? "Ask about the outcome" : "Ask a question"}><textarea rows={2} value={q} onChange={(x) => setQ(x.target.value)} /></Field>
            <button className="btn sm" disabled={q.length < 5} onClick={() => run(async () => { await post(`/supplier/opportunities/${id}/questions`, { question: q, kind: o.status === "awarded" ? "award_query" : "question" }); setQ(""); }, "Question sent")}>Send</button>
            <p className="small muted">Answers are shared with all suppliers without naming you.</p></>}
        </div>
      </div>
      {node}
    </>
  );
}
