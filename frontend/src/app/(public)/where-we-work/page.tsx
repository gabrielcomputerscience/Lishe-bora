import Link from "next/link";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { PageBanner } from "@/components/PageBanner";
import { faLocationDot } from "@/lib/icons";
import { publicGet } from "@/lib/server";

export const metadata = { title: "Where we work" };
type Area = { name: string; code: string; schools: number; sub_counties: { name: string; schools: string[] }[] };
const ACCENT = ["#507435", "#AB822D", "#75BA43", "#912E91"];

export default async function WhereWeWork() {
  const areas = (await publicGet<Area[]>("/pilot-areas")) ?? [];
  const total = areas.reduce((n, a) => n + a.schools, 0);
  return (
    <>
      <PageBanner slot="page:where-we-work" eyebrow="Where we work" title="Pilot counties and schools"
        sub={`${total} schools in ${areas.length} counties are part of the pilot. Suppliers in and around these counties can register for opportunities.`} />
      <section className="wrap sec">
        <div className="areagrid">
          {areas.map((a, i) => (
            <div key={a.code} className="card area" style={{ ["--ac" as string]: ACCENT[i % ACCENT.length] }}>
              <div className="row"><FontAwesomeIcon icon={faLocationDot} className="aico" /><h2>{a.name}</h2><span className="spacer" /><span className="pill p-green">{a.schools} schools</span></div>
              {a.sub_counties.map((s) => (
                <details key={s.name} className="faq" open={a.sub_counties.length <= 2}>
                  <summary>{s.name} <span className="small muted">· {s.schools.length} schools</span></summary>
                  <div className="chips" style={{ marginTop: 10 }}>{s.schools.map((n) => <span key={n} className="chip">{n}</span>)}</div>
                </details>))}
            </div>))}
        </div>
        {!areas.length && <div className="alert warn">The list of pilot areas is not available right now.</div>}
        <div className="ctacard" style={{ marginTop: 24 }}><b>Farmer, cooperative or trader in these counties?</b><Link className="btn gold lg" href="/register">Register as a supplier</Link></div>
      </section>
    </>
  );
}
