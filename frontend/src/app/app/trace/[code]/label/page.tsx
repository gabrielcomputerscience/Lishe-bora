"use client";
import { use, useEffect, useState } from "react";
import { get } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import type { Batch } from "@/lib/fulfilment";
import { kg } from "@/lib/planning";

/** Printable batch label: QR (links to the public verification page), code and key facts. */
export default function Label({ params }: { params: Promise<{ code: string }> }) {
  const { code } = use(params);
  const [b, setB] = useState<Batch | null>(null);
  useEffect(() => { get<Batch>(`/trace/${encodeURIComponent(code)}`).then(setB).catch(() => {}); }, [code]);
  if (!b) return <p style={{ padding: 20 }}>Loading label…</p>;
  return (
    <div style={{ padding: 20 }}>
      <style>{`@media print { .noprint, header.top, nav.side { display: none !important } main.main { padding: 0 !important } }`}</style>
      <div className="noprint row" style={{ marginBottom: 12 }}><button className="btn primary" onClick={() => window.print()}>Print</button>
        <span className="small muted">Print on label paper and stick one on each sack or crate.</span></div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} style={{ width: 300, border: "1px dashed #999", borderRadius: 6, padding: 10, display: "flex", gap: 10, alignItems: "center", breakInside: "avoid" }}>
            <img src={`/api/v1/batches/${b.id}/qr.svg`} alt={`QR for ${b.code}`} width={110} height={110} />
            <div style={{ fontSize: 12, lineHeight: 1.35 }}>
              <b style={{ fontSize: 14 }}>{b.code}</b><br />{b.commodity}{b.variety ? ` · ${b.variety}` : ""}<br />{b.grade || "Grade —"} · {kg(b.accepted_qty, b.unit)}<br />
              {b.location}<br />{b.expiry_date ? `Best before ${fmtDate(b.expiry_date)}` : ""}<br /><span style={{ color: "#555" }}>Scan to verify · LisheBora</span>
            </div>
          </div>))}
      </div>
    </div>
  );
}
