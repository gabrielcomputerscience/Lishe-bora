"use client";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { SupplierDocs } from "@/components/SupplierDocs";
import { ErrorBox, Field, PageHead, Pill, useToast } from "@/components/ui";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, human } from "@/lib/format";
import type { FoodCategory, Supplier } from "@/lib/types";

const NEXT: Record<string, { to: string; label: string; perm: string; kind?: string }[]> = {
  submitted: [{ to: "under_review", label: "Start review", perm: "sup:verify" }, { to: "rejected", label: "Reject", perm: "sup:reject", kind: "danger" }],
  under_review: [{ to: "approved", label: "Approve", perm: "sup:approve" }, { to: "submitted", label: "Return to supplier", perm: "sup:verify" },
    { to: "rejected", label: "Reject", perm: "sup:reject", kind: "danger" }],
  approved: [{ to: "prequalified", label: "Prequalify", perm: "sup:approve" }],
  prequalified: [{ to: "active", label: "Activate", perm: "sup:approve" }, { to: "suspended", label: "Suspend", perm: "sup:approve", kind: "danger" }],
  active: [{ to: "suspended", label: "Suspend", perm: "sup:approve", kind: "danger" }],
  suspended: [{ to: "active", label: "Reinstate", perm: "sup:approve" }],
};

export default function SupplierDetail() {
  const { id } = useParams<{ id: string }>();
  const { can } = useAuth();
  const [s, setS] = useState<Supplier | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [note, setNote] = useState("");
  const [cats, setCats] = useState<string[]>([]);
  const [foodCats, setFoodCats] = useState<FoodCategory[]>([]);
  useEffect(() => { get<FoodCategory[]>("/public/food-categories").then(setFoodCats).catch(() => {}); }, []);
  const catLabel = (k: string) => foodCats.find((c) => c.key === k)?.label ?? human(k);
  const { toast, node } = useToast();
  const load = useCallback(() => get<Supplier>(`/suppliers/${id}`).then((x) => { setS(x); setCats(x.approved_categories.length ? x.approved_categories : []); }).catch(setErr), [id]);
  useEffect(() => { load(); }, [load]);

  async function move(to: string) {
    setErr(null);
    try { setS(await post<Supplier>(`/suppliers/${id}/review`, { to_status: to, note, approved_categories: to === "prequalified" ? cats : undefined })); setNote(""); toast(`Status → ${human(to)}`); }
    catch (e) { setErr(e); }
  }
  async function inclusion(verified: boolean) {
    try { setS(await post<Supplier>(`/suppliers/${id}/inclusion`, { verified })); toast(verified ? "Inclusion status verified" : "Inclusion status not verified"); }
    catch (e) { setErr(e); }
  }
  if (!s) return <ErrorBox error={err} />;
  const actions = (NEXT[s.status] ?? []).filter((a) => can(a.perm));
  const inc = s.inclusion_claim as Record<string, string | number | null>;
  return (
    <>
      <PageHead crumb="Source › Supplier registry" title={s.legal_name} sub={`${human(s.supplier_type)} · ${s.county_name ?? ""}${s.sub_county ? " · " + s.sub_county : ""}`}>
        <Pill status={s.status} />
      </PageHead>
      <ErrorBox error={err} />
      <div className="grid g3" style={{ marginBottom: 16 }}>
        <div className="card"><h3>Profile</h3>
          <div className="small">Phone: <b>{s.phone}</b></div><div className="small">Email: {s.email || "—"}</div>
          <div className="small">Registration no.: {s.registration_no || "—"}</div><div className="small">Members: {s.members_count ?? "—"}</div>
          <div className="small">Commodities: {s.commodities.join(", ") || "—"}</div><div className="small">Registered: {fmtDate(s.created_at)}</div></div>
        <div className="card"><h3>Inclusion</h3>
          {s.inclusion_consent ? <>
            <div className="small">Leadership: <b>{human(String(inc.leadership ?? "—"))}</b></div>
            {inc.pct_women != null && <div className="small">Women members: {inc.pct_women}%</div>}
            {inc.pct_youth != null && <div className="small">Youth members: {inc.pct_youth}%</div>}
            <div style={{ margin: "10px 0" }}><Pill status={s.inclusion_verified ? "verified" : "uploaded"} label={s.inclusion_verified ? "Verified" : "Claimed, not verified"} /></div>
            {can("sup:verify") && <div className="row"><button className="btn sm primary" onClick={() => inclusion(true)}>Verify</button>
              <button className="btn sm" onClick={() => inclusion(false)}>Mark not verified</button></div>}
          </> : <p className="small muted">The supplier did not consent to sharing inclusion information.</p>}</div>
        <div className="card"><h3>Prequalification</h3>
          <div className="small">Approved categories: <b>{s.approved_categories.map(catLabel).join(", ") || "—"}</b></div>
          <div className="small">Valid until: {fmtDate(s.prequalified_until)}</div>
          {s.status_note && <div className="alert info small">{s.status_note}</div>}</div>
      </div>
      <SupplierDocs supplier={s} canUpload={can("sup:create")} canReview={can("sup:verify")} onChange={load} />
      {actions.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}><h2>Decision</h2>
          {s.status === "approved" && <Field label="Prequalify for categories"><div className="chips">{foodCats.map(({ key: c, label }) =>
            <label key={c} className="chip"><input type="checkbox" checked={cats.includes(c)} onChange={(e) => setCats(e.target.checked ? [...cats, c] : cats.filter((x) => x !== c))} /> {label}</label>)}</div></Field>}
          <Field label="Note (recorded in the audit trail and shown to the supplier)" id="nt"><textarea id="nt" rows={2} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
          <div className="row">{actions.map((a) => <button key={a.to} className={`btn ${a.kind ?? "primary"}`} onClick={() => move(a.to)}>{a.label}</button>)}</div>
          <p className="small muted">Approval requires the registration and payment documents to be verified. Reviewers and approvers are separate permissions.</p>
        </div>)}
      {node}
    </>
  );
}
