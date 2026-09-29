"use client";
import { useCallback, useEffect, useState } from "react";
import { ContractCard, POCard, type ContractT, type PO } from "@/components/Orders";
import { ErrorBox, PageHead, useToast } from "@/components/ui";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function Contracts() {
  const { can } = useAuth();
  const [tab, setTab] = useState<"contracts" | "orders">("contracts");
  const [cons, setCons] = useState<ContractT[]>([]);
  const [pos, setPos] = useState<PO[]>([]);
  const [qty, setQty] = useState<Record<string, string>>({});
  const [err, setErr] = useState<unknown>(null);
  const { toast, node } = useToast();
  const load = useCallback(() => { get<ContractT[]>("/contracts").then(setCons).catch(setErr); get<PO[]>("/purchase-orders").then(setPos).catch(() => {}); }, []);
  useEffect(() => { load(); }, [load]);
  async function callOff(c: ContractT) {
    setErr(null);
    try {
      await post(`/contracts/${c.id}/call-offs`, { lines: c.lines.filter((l) => Number(qty[l.id]) > 0).map((l) => ({ contract_line_id: l.id, quantity: qty[l.id] })) });
      toast("Call-off order issued"); setQty({}); load();
    } catch (x) { setErr(x); }
  }
  return (
    <>
      <PageHead crumb="Source" title="Contracts & purchase orders" sub="Funds are committed per contract. Call-offs cannot exceed the remaining contract balance." />
      <div className="tabs"><button className={`tab ${tab === "contracts" ? "on" : ""}`} onClick={() => setTab("contracts")}>Contracts ({cons.length})</button>
        <button className={`tab ${tab === "orders" ? "on" : ""}`} onClick={() => setTab("orders")}>Purchase orders ({pos.length})</button></div>
      <ErrorBox error={err} />
      {tab === "contracts" && <div className="stack">{cons.map((c) => <ContractCard key={c.id} c={c}>
        {c.kind === "framework" && c.status === "active" && can("con:create") && <div style={{ marginTop: 10 }}><b className="small">New call-off</b>
          <div className="row" style={{ marginTop: 6 }}>{c.lines.map((l) => <label key={l.id} className="small">{l.commodity}
            <input type="number" min={0} max={l.remaining} className="btn" style={{ width: 100, fontWeight: 400, marginLeft: 6 }} value={qty[l.id] ?? ""} onChange={(x) => setQty({ ...qty, [l.id]: x.target.value })} /></label>)}
            <button className="btn primary sm" onClick={() => callOff(c)}>Issue call-off</button></div></div>}
      </ContractCard>)}{!cons.length && <div className="card muted">No contracts yet.</div>}</div>}
      {tab === "orders" && <div className="stack">{pos.map((po) => <POCard key={po.id} po={po} />)}{!pos.length && <div className="card muted">No purchase orders yet.</div>}</div>}
      {node}
    </>
  );
}
