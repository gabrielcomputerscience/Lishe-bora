import Link from "next/link";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { BgVideo, bgStyle, getBackgrounds, HeroMedia } from "@/components/Backgrounds";
import { CountUp } from "@/components/CountUp";
import { HeroWaveBand, type ShowcaseScene } from "@/components/HeroWaves";
import { FOOD_IMAGE } from "@/lib/foodImages";
import { NewsCard } from "@/components/NewsCard";
import { NoticeTable } from "@/components/NoticeTable";
import { ReachMap, type Reach } from "@/components/ReachMap";
import { colourFor } from "@/lib/food";
import { faHandHoldingHeart, faLandmark, faLock, faMobileScreen, faMoneyBillWave, faQrcode, faScaleBalanced, faSchool, faWheatAwn, foodIcon, glanceIcon, LIVE_ICON } from "@/lib/icons";
import { publicGet } from "@/lib/server";
import { fontsHref, styleOf, type TextStyle } from "@/lib/textStyle";
import type { FoodCategory, NewsItem, Notice } from "@/lib/types";

type Home = {
  hero: { eyebrow?: string; title?: string; subtitle?: string; cta_label?: string; cta_link?: string; cta_hidden?: string;
    cta2_label?: string; cta2_link?: string; cta2_hidden?: string; styles?: Record<string, TextStyle> };
  stats: { show: boolean; items: { value: string; label: string }[]; styles?: Record<string, TextStyle> } | null;
  live: { key: string; value: number; label: string }[] | null;
  news: NewsItem[]; notices: Notice[];
};

const STEPS = [
  ["Schools plan", "Schools enter enrolment, menus and stock. The platform works out what food is needed."],
  ["Opportunities are published", "Demand is combined across schools and posted as open, fair sourcing notices."],
  ["Local suppliers bid", "Registered farmers, groups and traders bid. Bids are sealed until the deadline."],
  ["Deliver, verify, get paid", "Quality is checked, schools confirm receipt, and payment is tracked to settlement."],
];
// AATF Brand Manual colours: green, gold, amber, leaf, purple
const AUDIENCES = [
  ["Farmers, cooperatives & traders", "Register once, get SMS alerts for matching opportunities, bid online and track your payments.", "/p/for-suppliers", "#AB822D", "For suppliers", faWheatAwn],
  ["Schools", "Plan each term's food, check menus for variety, confirm deliveries on a phone even without network.", "/p/for-schools", "#75BA43", "For schools", faSchool],
  ["Counties & partners", "Run open procurement within budget, with approvals, sealed bids, quality checks and a full audit trail.", "/p/for-counties", "#507435", "For counties", faLandmark],
] as const;
const FEATURES = [
  ["Open and fair", "Every notice publishes its criteria in advance, and award decisions are made public.", faScaleBalanced],
  ["Sealed bids", "Bids are encrypted and stay closed until they are opened together after the deadline.", faLock],
  ["Works on any phone", "SMS alerts and one-time codes; delivery confirmation works offline and syncs later.", faMobileScreen],
  ["Quality you can trace", "Batches are inspected and labelled with QR codes, from the farmer group to the school kitchen.", faQrcode],
  ["Paid on time", "Invoices are matched to accepted deliveries, and suppliers can follow payment to settlement.", faMoneyBillWave],
  ["Inclusive by design", "Women-, youth- and PWD-led enterprises can declare their status, so inclusion can be monitored.", faHandHoldingHeart],
] as const;
const ACCENT = ["#507435", "#AB822D", "#75BA43", "#912E91", "#F9B916"];
// AATF brand colours (Brand Manual p.10) for the live figures and the programme figures
const LIVE_AC = ["#507435", "#AB822D", "#4E8A26", "#B7860B", "#912E91"];
const GLANCE_AC = ["#F9B916", "#75BA43", "#F9B916", "#E9A6E9"];

export default async function HomePage() {
  const [d, cats, reach, faq, bg] = await Promise.all([
    publicGet<Home>("/home"), publicGet<FoodCategory[]>("/food-categories"), publicGet<Reach>("/reach"),
    publicGet<{ question: string; answer: string }[]>("/faq"), getBackgrounds(),
  ]);
  const hero = d?.hero ?? {};
  const showcase: ShowcaseScene[] = (cats ?? []).map((c) => ({
    label: c.label, items: c.commodities.map((x) => x.name).join(", "),
    images: c.commodities.filter((x) => FOOD_IMAGE[x.code]).slice(0, 4).map((x) => ({ src: FOOD_IMAGE[x.code], alt: x.name })),
  })).filter((sc) => sc.images.length);
  const hs = hero.styles ?? {}, ss = d?.stats?.styles ?? {};
  const fonts = fontsHref({ ...hs, ...Object.fromEntries(Object.entries(ss).map(([k, v]) => [`s_${k}`, v])) });
  return (
    <>
      <section className="hero home-hero hasbg" style={bgStyle(bg.home_hero, true)}><BgVideo b={bg.home_hero} dark={true} />
        <div className={`wrap hero-in ${bg.home_hero_media?.hidden ? "hero-full" : "hero-split"}`}><div>
          {fonts && <link rel="stylesheet" href={fonts} precedence="default" />}
          <div className="eyebrow" style={styleOf(hs.eyebrow)}>{hero.eyebrow ?? "STEP School Feeding Project"}</div>
          <h1 style={styleOf(hs.title)}>{hero.title ?? "Nutritious school meals, sourced from local farmers"}</h1>
          {hero.subtitle && <p style={styleOf(hs.subtitle)}>{hero.subtitle}</p>}
          <div className="row">
            {hero.cta_hidden !== "yes" && <Link className="btn gold lg" href={hero.cta_link || "/register"} style={styleOf(hs.cta_label)}>{hero.cta_label || "Register as a supplier"}</Link>}
            {hero.cta2_hidden !== "yes" && <Link className="btn lg ghost" href={hero.cta2_link || "/opportunities"} style={styleOf(hs.cta2_label)}>{hero.cta2_label || "View open opportunities"}</Link>}
          </div>
        </div>
        <HeroMedia m={bg.home_hero_media} /></div>
        <HeroWaveBand showcase={showcase} parade={false} />
      </section>

      {!!d?.live?.length && (<>
        <section className="wrap livestats" aria-label="LisheBora today">
          {d.live.map((s, i) => (
            <div key={s.key} className="ls" style={{ ["--ac" as string]: LIVE_AC[i % LIVE_AC.length] } as React.CSSProperties}>
              <span className="ls-ico" aria-hidden="true"><FontAwesomeIcon icon={LIVE_ICON[s.key]} /></span>
              <b className="ls-num"><CountUp to={s.value} /></b><span className="ls-label">{s.label}</span></div>))}
        </section>
        <p className="wrap ls-note"><span className="live-dot" aria-hidden="true" /> Live figures from the platform, updated automatically.</p>
      </>)}
      {d?.stats && (
        <section className="glance" aria-label="Programme at a glance">
          <div className="wrap">
            <div className="glance-head"><span className="eyebrow">STEP School Feeding Project</span><h2 style={styleOf(ss.title)}>Programme at a glance</h2></div>
            <div className="glance-grid">{d.stats.items.map((s, i) => {
              const pct = /^\s*(\d{1,3}(?:\.\d+)?)\s*%\s*$/.exec(s.value);
              return (
                <div key={s.label} className="gl" style={{ ["--ac" as string]: GLANCE_AC[i % GLANCE_AC.length] } as React.CSSProperties}>
                  {pct ? <span className="gl-ring" style={{ ["--p" as string]: Math.min(100, parseFloat(pct[1])) } as React.CSSProperties} aria-hidden="true">
                    <FontAwesomeIcon icon={glanceIcon(s.label)} /></span>
                    : <span className="gl-ico" aria-hidden="true"><FontAwesomeIcon icon={glanceIcon(s.label)} /></span>}
                  <b className="gl-num" style={styleOf(ss.value)}>{s.value}</b>
                  <span className="gl-label" style={styleOf(ss.label)}>{s.label}</span>
                </div>);
            })}</div>
          </div>
        </section>
      )}

      <section className="bgsec hasbg" style={bgStyle(bg.home_audiences, false)}><BgVideo b={bg.home_audiences} dark={false} /><div className="wrap sec">
        <div className="sechead"><span className="kicker">Who it is for</span><h2>Built for everyone in the school food chain</h2></div>
        <div className="grid g3">{AUDIENCES.map(([t, x, href, c, k, ic]) => (
          <Link key={href} href={href} className="card aud" style={{ ["--ac" as string]: c }}>
            <span className="ico-badge" aria-hidden="true"><FontAwesomeIcon icon={ic} /></span><span className="kicker">{k}</span><h3>{t}</h3><p className="small muted">{x}</p>
            <span className="more">Learn more →</span></Link>))}</div>
      </div></section>

      <section className="howband hasbg" style={bgStyle(bg.home_how, false)}><BgVideo b={bg.home_how} dark={false} />
        <div className="wrap sec">
          <div className="sechead"><span className="kicker">How it works</span><h2>From the school plan to the supplier&apos;s payment</h2></div>
          <div className="grid g4 steps">{STEPS.map(([t, x], i) => (
            <div key={t} className="card howc"><span className="n">{i + 1}</span><h3>{t}</h3><p className="muted small">{x}</p></div>))}</div>
          <p style={{ marginTop: 16 }}><Link href="/how-it-works">Read the full process →</Link></p>
        </div>
      </section>

      {!!cats?.length && (
        <section className="bgsec hasbg" style={bgStyle(bg.home_food, false)}><BgVideo b={bg.home_food} dark={false} /><div className="wrap sec">
          <div className="sechead"><span className="kicker">Food &amp; nutrition</span><h2>{cats.length} food categories, one balanced plate</h2>
            <p className="muted" style={{ margin: "6px 0 0" }}>Menus, demand and supplier prequalification all use the food categories of the programme&apos;s school survey.</p></div>
          <div className="foodtiles">{cats.map((c) => {
            const pics = c.commodities.filter((x) => FOOD_IMAGE[x.code]).slice(0, 3);
            return (
              <div key={c.key} className="ftile" style={{ ["--fa" as string]: colourFor(c.group) }}>
                <div className="ftile-top">
                  <span className="ftile-ico" aria-hidden="true"><FontAwesomeIcon icon={foodIcon(c.key)} /></span>
                  <span className="ftile-group">{c.group}</span>
                  {!pics.length && <span className="ftile-big" aria-hidden="true"><FontAwesomeIcon icon={foodIcon(c.key)} /></span>}
                  <div className="ftile-pics" aria-hidden="true">{pics.map((x, k) => (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img key={x.code} src={FOOD_IMAGE[x.code]} alt="" loading="lazy" style={{ ["--k" as string]: k } as React.CSSProperties} />))}</div>
                </div>
                <div className="ftile-body"><b>{c.label}</b>
                  <div className="ftile-chips">{(c.commodities.length ? c.commodities.map((x) => x.name) : [c.group]).map((n) => <span key={n}>{n}</span>)}</div></div>
              </div>);
          })}</div>
        </div></section>
      )}

      {reach && (
        <section className="reachband hasbg" style={bgStyle(bg.home_areas, false)}><BgVideo b={bg.home_areas} dark={false} />
          <div className="wrap sec">
            <div className="sechead center"><span className="kicker">Where we work</span><h2 className="reach-title">Our reach</h2>
              <p className="muted">Live figures from the platform. Pilot counties are highlighted; hover or tap one for its figures.</p></div>
            <ReachMap data={reach} />
            <p className="center" style={{ marginTop: 18 }}><Link className="btn" href="/where-we-work">See every county and school →</Link></p>
          </div>
        </section>
      )}

      <section className="bgsec hasbg" style={bgStyle(bg.home_features, false)}><BgVideo b={bg.home_features} dark={false} /><div className="wrap sec">
        <div className="sechead"><span className="kicker">Why LisheBora</span><h2>Transparent, local and built for the field</h2></div>
        <div className="featgrid">{FEATURES.map(([t, x, ic], i) => (
          <div key={t} className="feat"><span className="ico-badge" style={{ ["--ac" as string]: ACCENT[i % ACCENT.length] }} aria-hidden="true"><FontAwesomeIcon icon={ic} /></span>
            <div><h3>{t}</h3><p className="small muted">{x}</p></div></div>))}</div>
      </div></section>

      <section className="wrap sec" style={{ paddingTop: 0 }}>
        <div className="row" style={{ marginBottom: 14 }}><h2>Open opportunities</h2><span className="spacer" /><Link href="/opportunities">See all →</Link></div>
        <NoticeTable rows={d?.notices ?? []} />
      </section>

      {!!d?.news.length && (
        <section className="wrap sec" style={{ paddingTop: 0 }}>
          <div className="row" style={{ marginBottom: 14 }}><h2>News &amp; updates</h2><span className="spacer" /><Link href="/news">All news →</Link></div>
          <div className="grid g3">{d.news.map((n) => <NewsCard key={n.slug} n={n} />)}</div>
        </section>
      )}

      {!!faq?.length && (
        <section className="wrap sec" style={{ paddingTop: 0 }}>
          <div className="grid g2" style={{ alignItems: "start" }}>
            <div><span className="kicker">Questions</span><h2>Frequently asked</h2>
              <p className="muted">Short answers to what suppliers and schools ask most often.</p><Link className="btn" href="/faq">All questions</Link></div>
            <div>{faq.slice(0, 4).map((f, i) => <details key={f.question} className="faq" open={i === 0}><summary>{f.question}</summary><p>{f.answer}</p></details>)}</div>
          </div>
        </section>
      )}

      <section className="wrap sec" style={{ paddingTop: 0 }}>
        <div className="aboutstrip">
          <div><span className="kicker">About AATF</span>
            <p>The African Agricultural Technology Foundation is an African-led, not-for-profit organisation, founded in 2003, working across
              Sub-Saharan Africa on agricultural technology transfer, seed systems and enabling policy environments.</p></div>
          <div className="row"><Link className="btn" href="/about">About LisheBora</Link><a className="btn" href="https://www.aatf-africa.org" target="_blank" rel="noreferrer">aatf-africa.org ↗</a></div>
        </div>
      </section>

      <section className="band hasbg" style={bgStyle(bg.home_band, true)}><BgVideo b={bg.home_band} dark={true} />
        <div className="wrap row" style={{ justifyContent: "space-between" }}>
          <div><h2>Are you a farmer, cooperative or trader?</h2>
            <p style={{ margin: "6px 0 0", color: "#E4ECDC" }}>Register once and receive SMS alerts for new opportunities in your area. Assisted registration is available.</p></div>
          <Link className="btn gold lg" href="/register">Register now</Link>
        </div>
      </section>
      {!d && <div className="wrap alert warn">The platform API is not reachable. Start the backend (see README).</div>}
    </>
  );
}
