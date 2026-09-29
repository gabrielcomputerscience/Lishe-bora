"use client";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faBowlFood, faChildren, faLayerGroup, faMapLocationDot, faPeopleGroup, faSchool } from "@fortawesome/free-solid-svg-icons";
import { useMemo, useState } from "react";
import { KENYA_COUNTIES, KENYA_VIEWBOX } from "@/lib/kenyaCounties";

type C = { code: string; name: string; schools: number; pupils: number; suppliers: number; food_varieties: number; sub_counties: string[] };
export type Reach = { counties: C[]; totals: { counties: number; schools: number; pupils: number; suppliers: number; food_varieties: number; food_categories: number } };

const fmt = (n: number) => n.toLocaleString("en-KE");
const norm = (s: string) => s.toUpperCase().replace(/ COUNTY$/, "").replace(/[^A-Z]/g, "");

/** "Our reach": an interactive map of Kenya's 47 counties inside an AATF-coloured ring. Pilot counties are highlighted;
 *  hover or tap one to see its schools, pupils, suppliers and food varieties. */
export function ReachMap({ data }: { data: Reach }) {
  const byKey = useMemo(() => Object.fromEntries(data.counties.map((c) => [norm(c.code), c])), [data]);
  const [hover, setHover] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const focusKey = sel ?? hover;
  const focus = focusKey ? byKey[focusKey] : undefined;
  const hoverName = focusKey ? KENYA_COUNTIES.find((k) => norm(k.code) === focusKey)?.name : undefined;
  const t = data.totals;
  const left = focus
    ? [[faSchool, focus.schools, "schools"], [faChildren, focus.pupils, "pupils in school plans"], [faLayerGroup, focus.sub_counties.length, "sub-counties"]]
    : [[faSchool, t.schools, "schools on the platform"], [faChildren, t.pupils, "pupils in school plans"], [faMapLocationDot, t.counties, "pilot counties"]];
  const right = focus
    ? [[faPeopleGroup, focus.suppliers, "suppliers registered"], [faBowlFood, focus.food_varieties, "food varieties offered"]]
    : [[faPeopleGroup, t.suppliers, "suppliers registered"], [faBowlFood, t.food_varieties, "food varieties offered"], [faLayerGroup, t.food_categories, "food categories supplied"]];
  const Stat = ({ s }: { s: (typeof left)[number] }) => (
    <div className="rstat"><FontAwesomeIcon icon={s[0] as typeof faSchool} className="rico" /><b>{fmt(s[1] as number)}</b><span>{s[2] as string}</span></div>);
  return (
    <div className="reach">
      <div className="rcol">{left.map((s) => <Stat key={s[2] as string} s={s} />)}</div>
      <div className="rmap">
        <svg viewBox="0 0 600 600" className="ring" aria-hidden="true">
          {[["#507435", 0], ["#AB822D", 0.25], ["#75BA43", 0.5], ["#F9B916", 0.75]].map(([c, o]) => (
            <circle key={c as string} cx="300" cy="300" r="286" fill="none" stroke={c as string} strokeWidth="22"
                    strokeDasharray={`${Math.PI * 572 * 0.25} ${Math.PI * 572}`} strokeDashoffset={-Math.PI * 572 * (o as number)} transform="rotate(-90 300 300)" />))}
          <circle cx="300" cy="300" r="270" fill="#fff" />
        </svg>
        <svg viewBox={KENYA_VIEWBOX} className="kenya" role="img" aria-label="Map of Kenya showing the pilot counties">
          {KENYA_COUNTIES.map((k) => {
            const key = norm(k.code), c = byKey[key], on = focusKey === key;
            return (
              <path key={k.code} d={k.d} className={`cty ${c ? "pilot" : ""} ${on ? "on" : ""}`} tabIndex={c ? 0 : -1}
                    onMouseEnter={() => setHover(key)} onMouseLeave={() => setHover(null)}
                    onClick={() => setSel(sel === key ? null : key)} onKeyDown={(e) => { if (e.key === "Enter") setSel(sel === key ? null : key); }}
                    aria-label={c ? `${c.name}: ${c.schools} schools` : k.name}><title>{c ? c.name : k.name}</title></path>);
          })}
        </svg>
        <div className="rlabel">{focus ? <><b>{focus.name}</b>{sel && <button className="btn sm" onClick={() => setSel(null)}>All counties</button>}</>
          : hoverName ? <span>{hoverName} · not in the pilot yet</span> : <span>Hover or tap a highlighted county</span>}</div>
      </div>
      <div className="rcol">{right.map((s) => <Stat key={s[2] as string} s={s} />)}</div>
    </div>
  );
}
