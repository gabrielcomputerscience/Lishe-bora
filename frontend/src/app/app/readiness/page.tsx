"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faCircleCheck, faCircleExclamation, faTriangleExclamation, faFileExcel, faRotate } from "@fortawesome/free-solid-svg-icons";
import { ErrorBox, PageHead } from "@/components/ui";
import { get } from "@/lib/api";

type Item = { area: string; title: string; status: "ok" | "todo" | "warn"; detail: string; link: string };
type R = { summary: { todo: number; warn: number; ok: number }; items: Item[] };
const ICON = { ok: faCircleCheck, warn: faTriangleExclamation, todo: faCircleExclamation };
const LABEL = { ok: "Done", warn: "Recommended", todo: "Needed before the pilot" };

/** Pilot readiness: live checklist of what still stands between this installation and a pilot with real data. */
export default function Readiness() {
  const [r, setR] = useState<R | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const load = useCallback(() => get<R>("/system/readiness").then(setR).catch(setErr), []);
  useEffect(() => { load(); }, [load]);
  const areas = r ? Array.from(new Set(r.items.map((i) => i.area))) : [];
  const pct = r ? Math.round((r.summary.ok / r.items.length) * 100) : 0;
  return (
    <>
      <PageHead crumb="Administration" title="Pilot readiness" sub="What still needs doing before the pilot starts with real schools, staff and suppliers. The list updates as you work.">
        <a className="btn" href="/api/v1/system/workbook"><FontAwesomeIcon icon={faFileExcel} /> Pilot data workbook</a>
        <button className="btn" onClick={load}><FontAwesomeIcon icon={faRotate} /> Check again</button>
      </PageHead>
      <ErrorBox error={err} />
      {r && <>
        <div className="grid g4" style={{ marginBottom: 16 }}>
          <div className="card kpi"><div className="l">Ready</div><div className="v">{pct}%</div><div className="rbar"><i style={{ width: `${pct}%` }} /></div></div>
          <div className="card kpi purple"><div className="l">Needed before the pilot</div><div className="v">{r.summary.todo}</div></div>
          <div className="card kpi gold"><div className="l">Recommended</div><div className="v">{r.summary.warn}</div></div>
          <div className="card kpi leaf"><div className="l">Done</div><div className="v">{r.summary.ok}</div></div>
        </div>
        <div className="card" style={{ marginBottom: 16 }}>
          <h3>How to load the real data</h3>
          <ol className="small">
            <li>Download the <a href="/api/v1/system/workbook">pilot data workbook</a>. It already lists the 32 schools and 36 foods.</li>
            <li>Fill the shaded cells: enrolment, GPS and NEMIS codes (Schools), staff and their roles (Staff), and reference prices (Prices).</li>
            <li>Upload the same workbook three times under <Link href="/app/system">System &amp; onboarding</Link>: Import schools, Import staff accounts, Import reference prices. Each shows a preview first.</li>
            <li>Nutrition officers set up the pilot menu and term dates under <Link href="/app/menus">Menus &amp; terms</Link>; finance officers add budget lines under <Link href="/app/budgets">Budgets</Link>.</li>
            <li>Fill the website contact details and pages under <Link href="/app/website">Website content</Link>, then open supplier registration.</li>
          </ol>
        </div>
        {areas.map((a) => (
          <div key={a} className="card" style={{ marginBottom: 12 }}><h3>{a}</h3>
            <div className="tablewrap"><table><tbody>{r.items.filter((i) => i.area === a).map((i) => (
              <tr key={i.title}><td style={{ width: 34 }}><FontAwesomeIcon icon={ICON[i.status]} className={`rd-${i.status}`} /></td>
                <td><b>{i.title}</b><div className="small muted">{i.detail}</div></td>
                <td className="small" style={{ whiteSpace: "nowrap" }}>{LABEL[i.status]}</td>
                <td className="r">{i.status !== "ok" && <Link className="btn sm" href={i.link}>Fix</Link>}</td></tr>))}</tbody></table></div></div>))}
      </>}
    </>
  );
}
