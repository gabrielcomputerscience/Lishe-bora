"use client";
import { useParams } from "next/navigation";
import { Fragment, useCallback, useEffect, useState } from "react";
import { WorkflowPanel } from "@/components/Workflow";
import { ErrorBox, Field, PageHead, Pill, useToast } from "@/components/ui";
import { get, post, put } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtDateTime, human } from "@/lib/format";
import { kg, ksh } from "@/lib/planning";
import { countdown, toLocalInput, type Criterion, type Event } from "@/lib/procurement";

type Clar = { id: string; kind: string; question: string; answer: string; asked_by: string | null; created_at: string; answered_at: string | null };
type BidRow = { id: string; supplier: string; status: string; submitted_at: string | null; revision: number; lots_bid: number; sha256: string;
  contents: { lines: { lot_id: string; unit_price: string; quantity: string }[]; delivery_plan: string } | null };
type Panel = { assigned: { user_id: string; name: string; coi_declared: boolean; has_conflict: boolean; submitted: boolean }[]; candidates: { id: string; name: string }[] };
const TABS = ["overview", "clarifications", "bids", "evaluation", "award"] as const;

export default function EventDetail() {
  const { id } = useParams<{ id: string }>();
  const { can } = useAuth();
  const [e, setE] = useState<Event | null>(null);
  const [tab, setTab] = useState<(typeof TABS)[number]>("overview");
  const [crit, setCrit] = useState<Criterion[]>([]);
  const [tw, setTw] = useState(60);
  const [closes, setCloses] = useState("");
  const [clar, setClar] = useState<Clar[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [amend, setAmend] = useState({ closes_at: "", note: "" });
  const [bids, setBids] = useState<{ opened: boolean; bids: BidRow[] } | null>(null);
  const [panel, setPanel] = useState<Panel | null>(null);
  const [pick, setPick] = useState<string[]>([]);
  const [err, setErr] = useState<unknown>(null);
  const { toast, node } = useToast();

  const load = useCallback(async () => {
    try {
      const x = await get<Event>(`/procurement-events/${id}`);
      setE(x); setCrit(x.criteria); setTw(x.technical_weight); setCloses(toLocalInput(x.closes_at));
      get<Clar[]>(`/procurement-events/${id}/clarifications`).then(setClar).catch(() => {});
      get<{ opened: boolean; bids: BidRow[] }>(`/procurement-events/${id}/bids`).then(setBids).catch(() => {});
      get<Panel>(`/procurement-events/${id}/evaluators`).then(setPanel).catch(() => {});
    } catch (x) { setErr(x); }
  }, [id]);
  useEffect(() => { load(); }, [load]);
  const run = async (fn: () => Promise<unknown>, ok: string) => { setErr(null); try { await fn(); toast(ok); await load(); } catch (x) { setErr(x); } };
  if (!e) return <ErrorBox error={err} />;
  const draft = e.status === "draft" && can("src:edit");
  const critSum = crit.reduce((a, c) => a + Number(c.max || 0), 0);
  const lotName = (lid: string) => e.lots.find((l) => l.id === lid)?.name ?? lid;

  return (
    <>
      <PageHead crumb="Source › Sourcing events" title={`${e.reference}`} sub={`${e.title} · ${e.method.toUpperCase()} · ${e.county ?? ""}`}>
        <Pill status={e.status} />
      </PageHead>
      <div className="grid g4" style={{ marginBottom: 16 }}>
        <div className="card kpi"><div className="l">Closes</div><div className="v" style={{ fontSize: 18 }}>{fmtDateTime(e.closes_at)}</div><div className="small muted">{e.status === "open" ? countdown(e.closes_at) : ""}</div></div>
        <div className="card kpi gold"><div className="l">Lots</div><div className="v">{e.lots.length}</div></div>
        <div className="card kpi leaf"><div className="l">Bids received</div><div className="v">{e.bids_received}</div></div>
        <div className="card kpi purple"><div className="l">Estimate (internal)</div><div className="v num" style={{ fontSize: 20 }}>{ksh(e.estimated_value)}</div></div>
      </div>
      <div className="tabs">{TABS.map((t) => <button key={t} className={`tab ${tab === t ? "on" : ""}`} onClick={() => setTab(t)}>
        {human(t)}{t === "clarifications" && clar.some((c) => !c.answer) ? " •" : ""}</button>)}</div>
      <ErrorBox error={err} />
      {e.workflow && e.workflow.can_act && <div style={{ marginBottom: 16 }}><WorkflowPanel wf={e.workflow} onDone={load} /></div>}

      {tab === "overview" && (<div className="grid" style={{ gridTemplateColumns: "3fr 2fr", alignItems: "start" }}>
        <div className="card"><h3>Lots</h3><div className="tablewrap"><table>
          <thead><tr><th>#</th><th>Lot</th><th className="r">Quantity</th><th>Specification</th></tr></thead>
          <tbody>{e.lots.map((l) => <tr key={l.id}><td>{l.lot_no}</td><td><b>{l.commodity}</b><div className="small muted">{l.name}</div>
            <div className="small muted">{l.schools.map((s) => s.name).join(", ")}</div></td><td className="r num">{kg(l.quantity, l.unit)}</td>
            <td className="small">{l.specification || "—"}</td></tr>)}</tbody></table></div>
          <p className="small muted">Eligibility: {e.eligibility || "Registered suppliers"} · Required documents: {e.required_docs.map(human).join(", ")} · Contract {fmtDate(e.contract_start)} – {fmtDate(e.contract_end)}</p></div>
        <div className="stack">
          <div className="card"><h3>Evaluation criteria</h3>
            <p className="small muted">Technical {tw} + financial {100 - tw} = 100. Financial score = weight × lowest price ÷ bid price.</p>
            {crit.map((c, i) => <div key={c.key} className="row" style={{ marginBottom: 6 }}>
              <span style={{ flex: 1 }} className="small">{c.label}{c.auto && <span className="pill p-green" style={{ marginLeft: 6 }}>automatic</span>}</span>
              <input aria-label={`Max ${c.label}`} type="number" className="btn" style={{ width: 70, fontWeight: 400 }} disabled={!draft} value={c.max}
                onChange={(x) => setCrit(crit.map((y, j) => (j === i ? { ...y, max: Number(x.target.value) } : y)))} /></div>)}
            <div className="row"><span className="small">Technical weight</span><span className="spacer" />
              <input aria-label="Technical weight" type="number" className="btn" style={{ width: 70, fontWeight: 400 }} disabled={!draft} value={tw} onChange={(x) => setTw(Number(x.target.value))} /></div>
            {Math.abs(critSum - tw) > 0.01 && <div className="alert warn small">Criteria add up to {critSum}; the technical weight is {tw}.</div>}
            {draft && <><Field label="Bids close at"><input type="datetime-local" value={closes} onChange={(x) => setCloses(x.target.value)} /></Field>
              <div className="row"><button className="btn" onClick={() => run(() => put(`/procurement-events/${id}`, { criteria: crit, technical_weight: tw, closes_at: new Date(closes).toISOString() }), "Saved")}>Save</button>
                {can("src:submit") && <button className="btn primary" onClick={() => run(async () => { await put(`/procurement-events/${id}`, { criteria: crit, technical_weight: tw, closes_at: new Date(closes).toISOString() }); await post(`/procurement-events/${id}/submit`); }, "Submitted for approval to publish")}>Submit for approval</button>}</div></>}
          </div>
          {e.status === "pending_approval" && !e.workflow?.can_act && <WorkflowPanel wf={e.workflow ?? null} onDone={load} />}
        </div></div>)}

      {tab === "clarifications" && (<div className="grid" style={{ gridTemplateColumns: "2fr 1fr", alignItems: "start" }}>
        <div className="stack">{clar.map((c) => <div key={c.id} className="card">
          <div className="row"><Pill status={c.kind === "amendment" ? "in_review" : c.answer ? "published" : "submitted"} label={human(c.kind)} />
            <span className="small muted">{c.asked_by ?? "Procurement"} · {fmtDateTime(c.created_at)}</span></div>
          <p style={{ margin: "8px 0" }}><b>{c.question}</b></p>
          {c.answer ? <p className="small">{c.answer}</p> : can("src:edit") && <>
            <textarea aria-label="Answer" rows={2} className="btn" style={{ width: "100%", fontWeight: 400 }} value={answers[c.id] ?? ""} onChange={(x) => setAnswers({ ...answers, [c.id]: x.target.value })} />
            <button className="btn sm primary" style={{ marginTop: 6 }} onClick={() => run(() => post(`/procurement-events/clarifications/${c.id}/answer`, { answer: answers[c.id] }), "Answer published to all suppliers")}>Publish answer</button></>}
        </div>)}{!clar.length && <div className="card muted">No questions yet.</div>}</div>
        {e.status === "open" && can("src:edit") && <div className="card"><h3>Formal amendment</h3>
          <p className="small muted">Changing the deadline notifies every eligible supplier and bidder, and is recorded in the audit trail.</p>
          <Field label="New closing time"><input type="datetime-local" value={amend.closes_at} onChange={(x) => setAmend({ ...amend, closes_at: x.target.value })} /></Field>
          <Field label="Reason (shown to suppliers)"><textarea rows={2} value={amend.note} onChange={(x) => setAmend({ ...amend, note: x.target.value })} /></Field>
          <button className="btn gold" disabled={!amend.closes_at || amend.note.length < 10} onClick={() => run(() => post(`/procurement-events/${id}/amend`, { closes_at: new Date(amend.closes_at).toISOString(), note: amend.note }), "Amendment issued")}>Issue amendment</button></div>}
      </div>)}

      {tab === "bids" && bids && (<div className="card">
        <div className="row"><h3>{bids.opened ? "Opening register" : "Sealed bids"}</h3><span className="spacer" />
          {e.status === "closed" && can("src:edit") && <button className="btn primary" onClick={() => run(() => post(`/procurement-events/${id}/open`), "Bids opened and recorded")}>Open bids</button>}</div>
        {!bids.opened && <div className="alert info">Bid contents are encrypted. They can be opened only after the closing time, and opening is recorded in the audit trail.</div>}
        <div className="tablewrap"><table><thead><tr><th>Supplier</th><th>Submitted</th><th className="r">Lots</th><th>Revision</th><th>Seal</th><th>Status</th></tr></thead>
          <tbody>{bids.bids.map((b) => <Fragment key={b.id}><tr><td><b>{b.supplier}</b></td><td className="small">{fmtDateTime(b.submitted_at)}</td><td className="r">{b.lots_bid}</td>
            <td>{b.revision}</td><td className="small num">{b.sha256}</td><td><Pill status={b.status} /></td></tr>
            {b.contents && <tr><td colSpan={6} className="small">{b.contents.lines.map((l) => `${lotName(l.lot_id)}: KSh ${Number(l.unit_price).toLocaleString()} × ${Number(l.quantity).toLocaleString()}`).join(" · ")}
              {b.contents.delivery_plan && <div className="muted">Delivery: {b.contents.delivery_plan}</div>}</td></tr>}</Fragment>)}
            {!bids.bids.length && <tr><td colSpan={6} className="muted">No bids yet.</td></tr>}</tbody></table></div></div>)}

      {tab === "evaluation" && panel && (<div className="stack">
        <div className="card"><h3>Evaluation panel</h3>
          <div className="tablewrap"><table><thead><tr><th>Evaluator</th><th>Conflict of interest</th><th>Scores</th></tr></thead>
            <tbody>{panel.assigned.map((a) => <tr key={a.user_id}><td><b>{a.name}</b></td>
              <td>{!a.coi_declared ? <Pill status="draft" label="Not declared" /> : a.has_conflict ? <Pill status="rejected" label="Conflict — excluded" /> : <Pill status="verified" label="No conflict" />}</td>
              <td>{a.submitted ? <Pill status="approved" label="Submitted" /> : <Pill status="draft" label="Pending" />}</td></tr>)}
              {!panel.assigned.length && <tr><td colSpan={3} className="muted">No evaluators assigned.</td></tr>}</tbody></table></div>
          {can("src:edit") && !["evaluated", "approved", "awarded", "cancelled"].includes(e.status) && <div className="row" style={{ marginTop: 12 }}>
            <div className="chips">{panel.candidates.filter((c) => !panel.assigned.some((a) => a.user_id === c.id)).map((c) =>
              <label key={c.id} className="chip"><input type="checkbox" checked={pick.includes(c.id)} onChange={(x) => setPick(x.target.checked ? [...pick, c.id] : pick.filter((y) => y !== c.id))} /> {c.name}</label>)}</div>
            <button className="btn" disabled={!pick.length} onClick={() => run(async () => { await post(`/procurement-events/${id}/evaluators`, { user_ids: pick }); setPick([]); }, "Evaluators assigned and notified")}>Assign</button></div>}
          {e.status === "under_evaluation" && can("src:edit") && <button className="btn primary" style={{ marginTop: 12 }} onClick={() => run(() => post(`/procurement-events/${id}/consolidate`), "Results consolidated")}>Consolidate results</button>}
        </div>
        {e.results && <div className="card"><div className="row"><h3>Results</h3><span className="spacer" /><span className="small muted">Evaluators: {e.results.evaluators.join(", ")}</span></div>
          {e.results.lots.map((lo) => <div key={lo.lot_id} style={{ marginTop: 12 }}><b>Lot {lo.lot_no}: {lo.name}</b> <span className="small muted">({kg(lo.quantity, lo.unit)})</span>
            <div className="tablewrap" style={{ margin: "6px 0 0" }}><table><thead><tr><th>Rank</th><th>Supplier</th><th className="r">Unit price</th><th className="r">Technical</th><th className="r">Financial</th><th className="r">Total</th><th>Notes</th></tr></thead>
              <tbody>{lo.bids.map((b) => <tr key={b.bid_id} style={lo.recommended === b.bid_id ? { background: "var(--green-50)" } : undefined}>
                <td>{b.rank ?? "—"}</td><td><b>{b.supplier}</b>{lo.recommended === b.bid_id && <span className="pill p-green" style={{ marginLeft: 6 }}>Recommended</span>}</td>
                <td className="r num">{Number(b.unit_price).toLocaleString()}</td><td className="r num">{b.technical_total}</td><td className="r num">{b.financial}</td><td className="r num"><b>{b.total}</b></td>
                <td className="small">{b.responsive ? Object.entries(b.technical).map(([k, v]) => `${k} ${v}`).join(" · ") : <span style={{ color: "var(--danger)" }}>{b.issues.join(" ")}</span>}</td></tr>)}</tbody></table></div></div>)}
          <p style={{ marginTop: 12 }}>Recommended total: <b>{ksh(e.results.recommended_total)}</b>{e.results.unawarded_lots.length > 0 && <span className="small" style={{ color: "var(--danger)" }}> · No responsive bid for lot(s) {e.results.unawarded_lots.join(", ")}</span>}</p>
          {e.status === "evaluated" && can("src:submit") && <button className="btn primary" onClick={() => run(() => post(`/procurement-events/${id}/recommend`), "Award recommendation submitted")}>Submit award recommendation</button>}
        </div>}
      </div>)}

      {tab === "award" && (<div className="grid g2" style={{ alignItems: "start" }}>
        <WorkflowPanel wf={e.status === "approved" && !e.workflow?.can_act ? e.workflow ?? null : null} history={e.history} onDone={load} />
        <div className="card"><h3>Outcome</h3>
          {e.status === "awarded" ? <><p>Awarded to <b>{e.awarded_to}</b> for <b>{ksh(e.awarded_value)}</b>.</p><p className="small muted">Contracts and purchase orders were created and suppliers notified. See Contracts &amp; POs.</p></>
            : <p className="muted small">The award is decided after evaluation, a commitment check by finance, and approval.</p>}
          {!["awarded", "cancelled", "approved"].includes(e.status) && can("src:edit") && <button className="btn danger sm" onClick={() => {
            const r = prompt("Reason for cancelling (sent to bidders)"); if (r && r.length >= 3) run(() => post(`/procurement-events/${id}/cancel`, { answer: r }), "Event cancelled"); }}>Cancel event</button>}
        </div></div>)}
      {node}
    </>
  );
}
