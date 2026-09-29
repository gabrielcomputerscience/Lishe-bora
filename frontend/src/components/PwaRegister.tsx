"use client";
import { useEffect, useState } from "react";

type BIPEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> };

/** Registers the service worker (production builds only) and offers "Install app" when the browser allows it. */
export function PwaRegister() {
  const [prompt, setPrompt] = useState<BIPEvent | null>(null);
  const [hidden, setHidden] = useState(false);
  useEffect(() => {
    if ("serviceWorker" in navigator && process.env.NODE_ENV === "production") navigator.serviceWorker.register("/sw.js").catch(() => {});
    const onPrompt = (e: Event) => { e.preventDefault(); setPrompt(e as BIPEvent); };
    window.addEventListener("beforeinstallprompt", onPrompt);
    try { setHidden(localStorage.getItem("lb_install_dismissed") === "1"); } catch { /* storage blocked */ }
    return () => window.removeEventListener("beforeinstallprompt", onPrompt);
  }, []);
  if (!prompt || hidden) return null;
  return (
    <div className="toast" role="dialog" aria-label="Install LisheBora" style={{ display: "flex", gap: 10, alignItems: "center" }}>
      <span>Install LisheBora on this device for quicker access and offline field work.</span>
      <button className="btn sm gold" onClick={async () => { await prompt.prompt(); setPrompt(null); }}>Install</button>
      <button className="btn sm ghost" style={{ color: "#fff" }} onClick={() => { setHidden(true); try { localStorage.setItem("lb_install_dismissed", "1"); } catch { /* ignore */ } }}>Not now</button>
    </div>
  );
}
