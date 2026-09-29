import { fmtBytes } from "@/lib/format";
import { publicGet } from "@/lib/server";
import { PageBanner } from "@/components/PageBanner";
export const metadata = { title: "Resources" };
type R = { id: string; title: string; description: string; file_name: string; size_bytes: number; has_file: boolean };
export default async function Resources() {
  const items = (await publicGet<R[]>("/resources")) ?? [];
  return (
    <><PageBanner slot="page:resources" eyebrow="Resources" title="Guides and downloads" sub="Checklists, guides and forms for suppliers, schools and county teams." />
    <section className="wrap sec narrow">
      <div className="card" style={{ marginTop: 16 }}>
        {items.length ? items.map((r) => (
          <div key={r.id} className="row" style={{ padding: "10px 0", borderBottom: "1px solid var(--line)" }}>
            <div><b>{r.title}</b><div className="small muted">{r.description}{r.has_file ? ` · ${fmtBytes(r.size_bytes)}` : ""}</div></div>
            <span className="spacer" />
            {r.has_file ? <a className="btn sm" href={`/api/v1/public/resources/${r.id}/file`}>Download</a> : <span className="small muted">Coming soon</span>}
          </div>)) : <p className="muted">No resources yet.</p>}
      </div>
    </section></>
  );
}
