"use client";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import { QrScan } from "@/components/QrScan";
import { PageHead } from "@/components/ui";

export default function TraceSearch() {
  const [code, setCode] = useState("");
  const router = useRouter();
  const go = useCallback((c: string) => router.push(`/app/trace/${c.trim().toUpperCase()}`), [router]);
  return (
    <>
      <PageHead crumb="Fulfil" title="Traceability" sub="Follow a batch from the farmers who supplied it, through inspection and storage, to the schools that received it." />
      <form className="card" style={{ maxWidth: 520 }} onSubmit={(e) => { e.preventDefault(); if (code.trim()) go(code); }}>
        <div className="field"><label htmlFor="bc">Batch code</label><input id="bc" value={code} onChange={(e) => setCode(e.target.value)} placeholder="BATCH-2026-000001" /></div>
        <div className="row"><button className="btn primary" type="submit">Trace</button><QrScan onCode={go} /></div>
      </form>
    </>
  );
}
