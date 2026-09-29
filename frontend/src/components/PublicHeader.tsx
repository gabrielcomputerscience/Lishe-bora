"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Logo } from "./Brand";

const NAV = [["/", "Home"], ["/about", "About"], ["/how-it-works", "How it works"], ["/opportunities", "Opportunities"],
  ["/where-we-work", "Where we work"], ["/news", "News"], ["/resources", "Resources"], ["/faq", "FAQ"], ["/contact", "Contact"]] as const;

export function PublicHeader() {
  const path = usePathname();
  const [open, setOpen] = useState(false);
  return (
    <header className="stop">
      <div className="wrap srow">
        <Link href="/" aria-label="LisheBora home"><Logo /></Link>
        <Link href="/" className="brandname">LisheBora</Link>
        <button className="iconbtn smenu" aria-label="Menu" aria-expanded={open} onClick={() => setOpen(!open)}>☰</button>
        <nav className={`snav ${open ? "open" : ""}`} aria-label="Main">
          {NAV.map(([href, label]) => (
            <Link key={href} href={href} onClick={() => setOpen(false)}
                  aria-current={(href === "/" ? path === "/" : path.startsWith(href)) ? "page" : undefined}>{label}</Link>
          ))}
        </nav>
        <div className="spacer" />
        <Link className="btn" href="/sign-in">Sign in</Link>
        <Link className="btn gold" href="/register">Register</Link>
      </div>
    </header>
  );
}
