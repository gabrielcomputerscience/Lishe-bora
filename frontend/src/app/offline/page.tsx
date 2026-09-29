import Link from "next/link";

export const metadata = { title: "Offline" };

export default function Offline() {
  return (
    <main className="wrap sec narrow" style={{ textAlign: "center" }}>
      <img src="/brand/aatf-logo.png" alt="AATF" style={{ height: 48, margin: "24px auto" }} />
      <h1>You are offline</h1>
      <p className="lead">This page has not been saved on this device yet. Pages you opened before (intake, inspection, deliveries) still work,
        and anything you record is kept on the device and sent when the connection returns.</p>
      <p><Link className="btn primary" href="/app">Try again</Link></p>
    </main>
  );
}
