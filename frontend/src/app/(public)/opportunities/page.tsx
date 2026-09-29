import { NoticeTable } from "@/components/NoticeTable";
import { fmtDate } from "@/lib/format";
import { publicGet } from "@/lib/server";
import type { Notice } from "@/lib/types";
import { PageBanner } from "@/components/PageBanner";

export const metadata = { title: "Opportunities" };
type Opps = { open: Notice[]; awards: { reference: string; title: string; awarded_to: string; value: string | null; awarded_at: string | null }[] };

export default async function Opportunities() {
  const d = await publicGet<Opps>("/opportunities");
  return (
    <><PageBanner slot="page:opportunities" eyebrow="Opportunities" title="Open sourcing notices" sub="To bid, sign in as a registered, prequalified supplier. Award decisions are published below for transparency." />
    <section className="wrap sec">
      <NoticeTable rows={d?.open ?? []} />
      <h2 style={{ margin: "32px 0 12px" }}>Recent awards</h2>
      {d?.awards.length ? (
        <div className="card"><div className="tablewrap"><table>
          <thead><tr><th>Reference</th><th>Title</th><th>Awarded to</th><th className="r">Value (KSh)</th><th>Date</th></tr></thead>
          <tbody>{d.awards.map((a) => <tr key={a.reference}><td><b>{a.reference}</b></td><td>{a.title}</td><td>{a.awarded_to}</td>
            <td className="r num">{a.value ? Number(a.value).toLocaleString("en-KE", { maximumFractionDigits: 0 }) : "—"}</td><td>{fmtDate(a.awarded_at)}</td></tr>)}</tbody>
        </table></div></div>
      ) : <p className="muted">Award decisions will be published here for transparency.</p>}
    </section></>
  );
}
