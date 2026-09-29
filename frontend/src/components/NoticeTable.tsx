import Link from "next/link";
import { fmtDateTime } from "@/lib/format";
import type { Notice } from "@/lib/types";

export function NoticeTable({ rows }: { rows: Notice[] }) {
  if (!rows.length) return <div className="card muted">There are no open opportunities right now. Register to get SMS alerts when new ones are published.</div>;
  return (
    <div className="card"><div className="tablewrap"><table>
      <thead><tr><th>Reference</th><th>Title</th><th>County</th><th>Eligibility</th><th>Closes</th><th /></tr></thead>
      <tbody>{rows.map((n) => (
        <tr key={n.reference}><td><b>{n.reference}</b></td><td>{n.title}</td><td>{n.county ?? "—"}</td>
          <td className="small">{n.eligibility || "Registered suppliers"}</td><td className="num">{fmtDateTime(n.closes_at)}</td>
          <td className="r"><Link className="btn sm primary" href="/sign-in">Sign in to bid</Link></td></tr>))}
      </tbody></table></div></div>
  );
}
