import { publicGet } from "@/lib/server";
import { PageBanner } from "@/components/PageBanner";
export const metadata = { title: "FAQ" };
export default async function Faq() {
  const items = (await publicGet<{ question: string; answer: string }[]>("/faq")) ?? [];
  return (
    <><PageBanner slot="page:faq" eyebrow="Help" title="Frequently asked questions" sub="Answers for suppliers, schools and county teams. Can't find yours? Send us a message." />
    <section className="wrap sec narrow">
      {items.map((f, i) => <details key={f.question} className="faq" open={i === 0}><summary>{f.question}</summary><p>{f.answer}</p></details>)}
    </section></>
  );
}
