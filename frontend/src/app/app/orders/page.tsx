"use client";
import { useCallback, useEffect, useState } from "react";
import { ContractCard, POCard, type ContractT, type PO } from "@/components/Orders";
import { ErrorBox, PageHead, useToast } from "@/components/ui";
import { get, post } from "@/lib/api";

export default function MyOrders() {
  const [d, setD] = useState<{ contracts: ContractT[]; orders: PO[] } | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const { toast, node } = useToast();
  const load = useCallback(() => get<{ contracts: ContractT[]; orders: PO[] }>("/supplier/orders").then(setD).catch(setErr), []);
  useEffect(() => { load(); }, [load]);
  return (
    <>
      <PageHead crumb="Supplier" title="My contracts & orders" sub="Acknowledge each purchase order to confirm you will deliver." />
      <ErrorBox error={err} />
      <h2 style={{ margin: "4px 0 10px" }}>Purchase orders</h2>
      <div className="stack">{d?.orders.map((po) => <POCard key={po.id} po={po}>
        {po.status === "issued" && <button className="btn primary" onClick={async () => { try { await post(`/supplier/orders/${po.id}/acknowledge`); toast("Order acknowledged"); load(); } catch (x) { setErr(x); } }}>Acknowledge order</button>}
      </POCard>)}{d && !d.orders.length && <div className="card muted">No purchase orders yet.</div>}</div>
      <h2 style={{ margin: "24px 0 10px" }}>Contracts</h2>
      <div className="stack">{d?.contracts.map((c) => <ContractCard key={c.id} c={c} />)}{d && !d.contracts.length && <div className="card muted">No contracts yet.</div>}</div>
      {node}
    </>
  );
}
