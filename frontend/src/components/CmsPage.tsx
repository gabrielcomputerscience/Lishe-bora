import Link from "next/link";
import { notFound } from "next/navigation";
import { Markdown } from "@/components/Markdown";
import { PageBanner } from "@/components/PageBanner";
import { publicGet } from "@/lib/server";

const EYEBROW: Record<string, string> = { "for-suppliers": "For suppliers", "for-schools": "For schools", "for-counties": "For counties & partners",
  about: "About", "how-it-works": "How it works", privacy: "Legal", terms: "Legal" };
const CTA: Record<string, [string, string, string]> = {
  "for-suppliers": ["Ready to supply schools?", "/register", "Register as a supplier"],
  "for-schools": ["Is your school in a pilot area?", "/contact", "Contact the programme team"],
  "for-counties": ["Want to see the platform in action?", "/contact", "Get in touch"],
  "how-it-works": ["See what is open now", "/opportunities", "View opportunities"],
};

export async function CmsPage({ slug }: { slug: string }) {
  const pg = await publicGet<{ title: string; body: string }>(`/pages/${slug}`);
  if (!pg) notFound();
  const cta = CTA[slug];
  return (
    <>
      <PageBanner slot={`page:${slug}`} eyebrow={EYEBROW[slug] ?? "LisheBora"} title={pg.title} />
      <section className="wrap sec narrow cmsbody"><Markdown>{pg.body}</Markdown>
        {cta && <div className="ctacard"><b>{cta[0]}</b><Link className="btn gold lg" href={cta[1]}>{cta[2]}</Link></div>}
      </section>
    </>
  );
}
