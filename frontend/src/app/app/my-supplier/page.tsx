"use client";
import { useCallback, useEffect, useState } from "react";
import { PaymentDetails } from "@/components/PaymentDetails";
import { SupplierDocs } from "@/components/SupplierDocs";
import { ErrorBox, PageHead, Pill } from "@/components/ui";
import { get } from "@/lib/api";
import { human } from "@/lib/format";
import type { Supplier } from "@/lib/types";

export default function MySupplier() {
  const [s, setS] = useState<Supplier | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const load = useCallback(() => get<Supplier>("/suppliers/me").then(setS).catch(setErr), []);
  useEffect(() => { load(); }, [load]);
  if (!s) return <ErrorBox error={err} />;
  return (
    <>
      <PageHead crumb="Supplier" title={s.legal_name} sub={`${human(s.supplier_type)} · ${s.county_name ?? ""}`}><Pill status={s.status} /></PageHead>
      {s.status_note && <div className="alert info">Message from the county: {s.status_note}</div>}
      {s.approved_categories.length > 0 && <div className="alert info">Prequalified for: <b>{s.approved_categories.map(human).join(", ")}</b></div>}
      <SupplierDocs supplier={s} canUpload canReview={false} onChange={load} />
      <PaymentDetails />
    </>
  );
}
