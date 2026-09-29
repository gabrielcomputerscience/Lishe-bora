"use client";
import { useState } from "react";
import { ErrorBox, Pill } from "@/components/ui";
import { post } from "@/lib/api";
import { fmtDateTime, human } from "@/lib/format";

export type WF = {
  id: string; name: string; status: string; title: string; entity: string; entity_id: string; entity_ref: string;
  stage_index: number; stages: { key: string; label: string; permission: string }[]; current_stage: string | null;
  due_at: string | null; overdue: boolean; amount: number | null; started_at: string;
  history: { stage: string; action: string; by: string; note: string; at: string }[];
  can_act?: boolean; why_not?: string; link?: string;
};

export function StageBar({ wf }: { wf: WF }) {
  return (
    <div className="steps">
      <div className="step done">Submitted</div>
      {wf.stages.map((s, i) => {
        const done = wf.status === "approved" || i < wf.stage_index;
        const cur = wf.status === "active" && i === wf.stage_index;
        return <div key={s.key} className={`step ${done ? "done" : ""} ${cur ? "cur" : ""}`}>{s.label}</div>;
      })}
    </div>
  );
}

export function History({ items }: { items: WF["history"] }) {
  if (!items.length) return null;
  return (
    <div className="small" style={{ marginTop: 10 }}>
      {items.map((h, i) => (
        <div key={i} style={{ padding: "6px 0", borderTop: "1px solid var(--line)" }}>
          <b>{human(h.action)}</b> · {h.by} · <span className="muted">{fmtDateTime(h.at)}</span>
          {h.note && <div className="muted">“{h.note}”</div>}
        </div>))}
    </div>
  );
}

/** Approval panel: shows progress, history and — if the signed-in user may act — approve / return / reject. */
export function WorkflowPanel({ wf, history, onDone }: { wf: WF | null; history?: WF["history"]; onDone: () => void }) {
  const [note, setNote] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  if (!wf) return history?.length ? <div className="card"><h3>Approval history</h3><History items={history} /></div> : null;
  async function act(action: string) {
    setErr(null); setBusy(true);
    try { await post(`/workflow/${wf!.id}/act`, { action, note }); setNote(""); onDone(); }
    catch (e) { setErr(e); } finally { setBusy(false); }
  }
  return (
    <div className="card">
      <div className="row"><h3>{wf.name}</h3><span className="spacer" />
        {wf.overdue ? <Pill status="rejected" label="Overdue" /> : <Pill status="in_review" label={wf.current_stage ?? human(wf.status)} />}</div>
      <StageBar wf={wf} />
      {wf.due_at && <p className="small muted" style={{ marginTop: -6 }}>Due {fmtDateTime(wf.due_at)}</p>}
      {wf.can_act ? (
        <>
          <div className="field"><label htmlFor="wfnote">Comment (needed to return or reject)</label>
            <textarea id="wfnote" rows={2} value={note} onChange={(e) => setNote(e.target.value)} /></div>
          <ErrorBox error={err} />
          <div className="row">
            <button className="btn primary" disabled={busy} onClick={() => act("approve")}>Approve</button>
            <button className="btn" disabled={busy} onClick={() => act("return")}>Return for changes</button>
            <button className="btn danger" disabled={busy} onClick={() => act("reject")}>Reject</button>
          </div>
        </>
      ) : wf.why_not ? <p className="small muted">{wf.why_not}</p> : null}
      <History items={wf.history} />
    </div>
  );
}
