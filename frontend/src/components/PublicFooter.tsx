/* eslint-disable @next/next/no-img-element */
import Link from "next/link";
import { publicGet } from "@/lib/server";

type Site = { phone?: string; sms_code?: string; whatsapp?: string; email?: string; address?: string; hours?: string; languages?: string };


export async function PublicFooter() {
  const site = (await publicGet<Site>("/site")) ?? {};
  const any = site.phone || site.sms_code || site.email || site.whatsapp || site.address;
  return (
    <footer className="sfoot">
      <div className="wrap fgrid">
        <div><span className="flogo"><img src="/brand/aatf-logo-tagline.png" alt="AATF — Prosperity through technology" style={{ height: 48, display: "block" }} /></span>
          <p className="small" style={{ marginTop: 12 }}>LisheBora e-Sourcing Platform · STEP School Feeding Project</p>
          <p className="small">African Agricultural Technology Foundation · <a href="https://www.aatf-africa.org" style={{ display: "inline" }}>aatf-africa.org</a></p></div>
        <div><b>Platform</b><Link href="/opportunities">Opportunities</Link><Link href="/how-it-works">How it works</Link>
          <Link href="/where-we-work">Where we work</Link>
          <Link href="/resources">Resources</Link><Link href="/faq">FAQ</Link></div>
        <div><b>For you</b><Link href="/p/for-suppliers">Suppliers</Link><Link href="/p/for-schools">Schools</Link>
          <Link href="/p/for-counties">Counties &amp; partners</Link><Link href="/news">News</Link></div>
        <div><b>Help</b><Link href="/contact">Contact &amp; grievances</Link><Link href="/p/privacy">Privacy notice</Link>
          <Link href="/p/terms">Terms of use</Link></div>
        <div><b>Helpdesk</b>
          {site.phone && <a href={`tel:${site.phone.replace(/\s/g, "")}`}>Phone: {site.phone}</a>}
          {site.sms_code && <span>SMS: {site.sms_code}</span>}
          {site.whatsapp && <span>WhatsApp: {site.whatsapp}</span>}
          {site.email && <a href={`mailto:${site.email}`}>{site.email}</a>}
          {site.address && <span>{site.address}</span>}
          {site.hours && <span>{site.hours}</span>}
          {!any && <Link href="/contact">Send us a message</Link>}
          <span>{site.languages || "English · Kiswahili"}</span></div>
      </div>
    </footer>
  );
}
