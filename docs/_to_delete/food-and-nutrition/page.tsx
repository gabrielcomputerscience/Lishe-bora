import Link from "next/link";
import { PageBanner } from "@/components/PageBanner";
import { colourFor } from "@/lib/food";
import { publicGet } from "@/lib/server";
import type { FoodCategory } from "@/lib/types";

export const metadata = { title: "Food & nutrition" };

export default async function Foods() {
  const cats = (await publicGet<FoodCategory[]>("/food-categories")) ?? [];
  const groups = Array.from(new Set(cats.map((c) => c.group).filter(Boolean)));
  return (
    <>
      <PageBanner eyebrow="Food & nutrition" title="The foods on school menus"
        sub={`LisheBora uses the ${cats.length} food categories of the programme's school survey. Every food a supplier offers and every menu a school plans is organised by these categories.`} />
      <section className="wrap sec">
        <div className="legend">{groups.map((g) => { const [a, b] = colourFor(g); return <span key={g}><i style={{ background: a, borderColor: b }} />{g}</span>; })}</div>
        <div className="foodgrid">
          {cats.map((c, i) => { const [a, b] = colourFor(c.group); return (
            <div key={c.key} className="foodcard" style={{ ["--fa" as string]: a, ["--fb" as string]: b }}>
              <div className="fhead"><span className="fdia"><em>{i + 1}</em></span><div><h3>{c.label}</h3>{c.group && <span className="small muted">{c.group}</span>}</div></div>
              <div className="chips">{c.commodities.map((x) => <span key={x.code} className="chip">{x.name}</span>)}
                {!c.commodities.length && <span className="small muted">No items listed yet</span>}</div>
            </div>); })}
        </div>
      </section>
      <section className="wrap sec" style={{ paddingTop: 0 }}>
        <div className="grid g3">
          <div className="card"><h3>Variety on every menu</h3><p className="small muted">Menus are checked for how many food groups they cover over the week before schools use them.</p></div>
          <div className="card"><h3>Quantities worked out for you</h3><p className="small muted">From enrolment, feeding days and portions, the platform calculates how much of each food a school needs for the term.</p></div>
          <div className="card"><h3>Grown close to the school</h3><p className="small muted">Suppliers are prequalified for the categories they grow or trade, so opportunities reach the right local producers.</p></div>
        </div>
        <p className="small muted" style={{ marginTop: 14 }}>The grouping used for the menu-variety check is a platform default for nutrition officers to confirm. <Link href="/p/for-suppliers">Supplying these foods?</Link></p>
      </section>
    </>
  );
}
