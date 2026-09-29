"use client";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ErrorBox, PageHead, Pill, useToast } from "@/components/ui";
import { get, post, put } from "@/lib/api";
import type { Event } from "@/lib/procurement";

type WBid = { id: string; supplier: string; supplier_type: string; inclusion_verified: boolean; eligibility_issues: string[]; auto_scores: Record<string, number>;
  contents: { lines: { lot_id: string; unit_price: string; quantity: string; notes: string }[]; delivery_plan: string; technical_notes: string } };
type WS = { event: Event; assignment: { coi_declared: boolean; has_conflict: boolean; submitted: boolean; scores: Record<string, Record<string, number | string>> }; bids: WBid[] | null };

export default function Workspace() {
  const { id } = useParams<{ id: string }>();
  const [w, setW] = useState<WS | null>(null);
  const [scores, setScores] = useState<Record<string, Record<string, number | string>>>({});
  const [coi, setCoi] = useState<{ has_conflict: boolean; statement: string }>({ has_conflict: false, statement: "" });
  const [agree, setAgree] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const { toast, node } = useToast();
  const load = useCallback(() => get<WS>(`/evaluations/${id}`).then((x) => { setW(x); setScores(x.assignment.scores || {}); }).catch(setErr), [id]);
  useEffect(() => { load(); }, [load]);
  const run = async (fn: () => Promise<unknown>, ok: string) => { setErr(null); try { await fn(); toast(ok); await load(); } catch (x) { setErr(x); } };
  if (!w) return <ErrorBox error={err} />;
  const e = w.event, a = w.assignment;
  const manual = e.criteria.filter((c) => !c.auto);
  const locked = a.submitted || e.status !== "under_evaluation";
  const lot = (lid: string) => e.lots.find((l) => l.id === lid);

  return (
    <>
      <PageHead crumb="Source › My evaluations" title={e.reference} sub={e.title}><Pill status={e.status} /></PageHead>
      <ErrorBox error={err} />
      {!a.coi_declared && (<div className="card" style={{ maxWidth: 720 }}>
        <h2>Conflict-of-interest declaration</h2>
        <p className="muted">You must declare before any bid is shown to you (BR-015). If you have a conflict you will be removed from scoring this event.</p>
        <label className="chk" style={{ marginBottom: 10 }}><input type="radio" name="coi" checked={!coi.has_conflict} onChange={() => setCoi({ ...coi, has_conflict: false })} />
          I have no financial, family or business interest in any bidder, and I will keep bid information confidential.</label>
        <label className="chk" style={{ marginBottom: 10 }}><input type="radio" name="coi" checked={coi.has_conflict} onChange={() => setCoi({ ...coi, has_conflict: true })} />
          I have a possible conflict of interest.</label>
        <div className="field"><label htmlFor="st">Statement {coi.has_conflict ? "(describe the conflict)" : "(confirm in your own words)"}</label>
          <textarea id="st" rows={2} value={coi.statement} onChange={(x) => setCoi({ ...coi, statement: x.target.value })} /></div>
        <label className="small"><input type="checkbox" checked={agree} onChange={(x) => setAgree(x.target.checked)} /> I understand this declaration is recorded in the audit trail.</label>
        <div className="row" style={{ marginTop: 10 }}><button className="btn primary" disabled={!agree || coi.statement.length < 10}
          onClick={() => run(() => post(`/evaluations/${id}/coi`, coi), "Declaration recorded")}>Submit declaration</button></div>
      </div>)}
      {a.coi_declared && a.has_conflict && <div className="alert warn">You declared a conflict of interest and are excluded from scoring this event. Thank you for declaring it.</div>}
      {a.coi_declared && !a.has_conflict && !w.bids && <div className="alert info">Bids will appear here once they have been formally opened after the closing time.</div>}
      {w.bids && (<>
        <div className="alert info">Score each criterion. The inclusion score is automatic: full marks only when the supplier's women/youth/PWD-led status has been verified. Financial scores are calculated from prices.</div>
        <div className="stack">{w.bids.map((b) => (
          <div key={b.id} className="card">
            <div className="row"><h3>{b.supplier}</h3><span className="small muted">{b.supplier_type}</span>
              {b.inclusion_verified && <span className="pill p-green">Inclusion verified</span>}<span className="spacer" />
              {b.eligibility_issues.length > 0 && <span className="pill p-red">Eligibility issue</span>}</div>
            {b.eligibility_issues.map((i) => <div key={i} className="alert bad small">{i}</div>)}
            <div className="tablewrap" style={{ margin: "8px 0" }}><table><thead><tr><th>Lot</th><th className="r">Unit price (KSh)</th><th className="r">Quantity offered</th><th>Notes</th></tr></thead>
              <tbody>{b.contents.lines.map((l) => <tr key={l.lot_id}><td>{lot(l.lot_id)?.commodity} <span className="muted small">lot {lot(l.lot_id)?.lot_no}</span></td>
                <td className="r num">{Number(l.unit_price).toLocaleString()}</td><td className="r num">{Number(l.quantity).toLocaleString()} {lot(l.lot_id)?.unit}</td><td className="small">{l.notes}</td></tr>)}</tbody></table></div>
            {b.contents.delivery_plan && <p className="small"><b>Delivery plan:</b> {b.contents.delivery_plan}</p>}
            {b.contents.technical_notes && <p className="small"><b>Technical:</b> {b.contents.technical_notes}</p>}
            <div className="grid g4">{manual.map((c) => <div key={c.key} className="field"><label>{c.label} (0–{c.max})</label>
              <input type="number" min={0} max={c.max} step={0.5} disabled={locked} value={String(scores[b.id]?.[c.key] ?? "")}
                onChange={(x) => setScores({ ...scores, [b.id]: { ...(scores[b.id] || {}), [c.key]: x.target.value === "" ? "" : Number(x.target.value) } })} /></div>)}
              {Object.entries(b.auto_scores).map(([k, v]) => <div key={k} className="field"><label>{k} (automatic)</label><input disabled value={v} /></div>)}</div>
            <div className="field"><label>Comment</label><input disabled={locked} value={String(scores[b.id]?._comment ?? "")}
              onChange={(x) => setScores({ ...scores, [b.id]: { ...(scores[b.id] || {}), _comment: x.target.value } })} /></div>
          </div>))}</div>
        {!locked && <div className="row" style={{ marginTop: 16, justifyContent: "flex-end" }}>
          <button className="btn" onClick={() => run(() => put(`/evaluations/${id}/scores`, { scores: clean(scores) }), "Scores saved")}>Save scores</button>
          <button className="btn primary" onClick={() => run(async () => { await put(`/evaluations/${id}/scores`, { scores: clean(scores) }); await post(`/evaluations/${id}/submit`); }, "Evaluation submitted")}>Submit my evaluation</button></div>}
        {a.submitted && <div className="alert info">Your scores are submitted and locked.</div>}
      </>)}
      {node}
    </>
  );
}
function clean(s: Record<string, Record<string, number | string>>) {
  return Object.fromEntries(Object.entries(s).map(([k, v]) => [k, Object.fromEntries(Object.entries(v).filter(([, x]) => x !== ""))]));
}
