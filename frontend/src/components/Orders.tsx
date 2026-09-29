"use client";
import { Pill } from "@/components/ui";
import { fmtDate, fmtDateTime } from "@/lib/format";
import { kg, ksh } from "@/lib/planning";

export type CLine = { id: string; commodity: string; unit: string; quantity: number; unit_price: number; quantity_ordered: number; remaining: number };
export type ContractT = { id: string; reference: string; supplier: string; kind: string; value: number; ordered_value: number; remaining_value: number;
  starts_on: string; ends_on: string; status: string; alerts: string[]; lines: CLine[] };
export type PO = { id: string; reference: string; contract: string; supplier: string; status: string; total: number; delivery_window: string; issued_at: string;
  acknowledged_at: string | null; lines: { commodity: string; unit: string; quantity: number; unit_price: number; value: number; schools: { name: string; qty: string }[];
  dispatched_qty?: number; accepted_qty?: number; rejected_qty?: number }[] };

export function ContractCard({ c, children }: { c: ContractT; children?: React.ReactNode }) {
  const used = c.value ? (Number(c.ordered_value) / Number(c.value)) * 100 : 0;
  return (
    <div className="card">
      <div className="row"><h3>{c.reference}</h3><span className="small muted">{c.supplier} · {c.kind === "framework" ? "Framework agreement" : "Purchase contract"}</span>
        <span className="spacer" />{c.alerts.map((a) => <span key={a} className="pill p-amber">{a}</span>)}<Pill status={c.status} /></div>
      <p className="small muted" style={{ margin: "4px 0 8px" }}>{fmtDate(c.starts_on)} – {fmtDate(c.ends_on)} · value {ksh(c.value)} · ordered {ksh(c.ordered_value)} · remaining {ksh(c.remaining_value)}</p>
      <div style={{ height: 8, background: "#EEF0E9", borderRadius: 6, overflow: "hidden", marginBottom: 8 }}><div style={{ width: `${Math.min(100, used)}%`, height: "100%", background: "var(--green)" }} /></div>
      <div className="tablewrap"><table><thead><tr><th>Commodity</th><th className="r">Contracted</th><th className="r">Ordered</th><th className="r">Remaining</th><th className="r">Unit price</th></tr></thead>
        <tbody>{c.lines.map((l) => <tr key={l.id}><td>{l.commodity}</td><td className="r num">{kg(l.quantity, l.unit)}</td><td className="r num">{kg(l.quantity_ordered, l.unit)}</td>
          <td className="r num">{kg(l.remaining, l.unit)}</td><td className="r num">{Number(l.unit_price).toLocaleString()}</td></tr>)}</tbody></table></div>
      {children}
    </div>
  );
}

export function POCard({ po, children }: { po: PO; children?: React.ReactNode }) {
  return (
    <div className="card">
      <div className="row"><h3>{po.reference}</h3><span className="small muted">{po.supplier} · contract {po.contract} · issued {fmtDateTime(po.issued_at)}</span><span className="spacer" /><Pill status={po.status} /></div>
      <div className="tablewrap" style={{ marginTop: 8 }}><table><thead><tr><th>Commodity</th><th className="r">Quantity</th><th className="r">Unit price</th><th className="r">Value</th><th className="r">Delivered & accepted</th><th>Deliver to</th></tr></thead>
        <tbody>{po.lines.map((l, i) => <tr key={i}><td>{l.commodity}</td><td className="r num">{kg(l.quantity, l.unit)}</td><td className="r num">{Number(l.unit_price).toLocaleString()}</td>
          <td className="r num">{ksh(l.value)}</td>
          <td className="r num">{kg(l.accepted_qty ?? 0, l.unit)}{Number(l.rejected_qty) ? <div className="small muted">{kg(l.rejected_qty, l.unit)} rejected</div> : null}</td><td className="small">{l.schools.map((s) => `${s.name} (${Number(s.qty).toLocaleString()})`).join(", ") || "—"}</td></tr>)}</tbody></table></div>
      <p className="small" style={{ marginTop: 8 }}>Total <b>{ksh(po.total)}</b>{po.acknowledged_at ? ` · acknowledged ${fmtDateTime(po.acknowledged_at)}` : ""}</p>
      {children}
    </div>
  );
}
