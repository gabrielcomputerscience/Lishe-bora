"use client";
/** Draft → review → publish buttons shared by the website editors. */
export function FlowButtons({ status, onAct, can, republish = false }: { status: string; onAct: (a: string) => void; can: (p: string) => boolean; republish?: boolean }) {
  return (
    <div className="row" style={{ gap: 6 }}>
      {status === "draft" && can("cms:submit") && <button className="btn sm" onClick={() => onAct("submit")}>Submit for review</button>}
      {status === "in_review" && can("cms:reject") && <button className="btn sm" onClick={() => onAct("return")}>Return to editor</button>}
      {["draft", "in_review"].includes(status) && can("cms:approve") && <button className="btn sm primary" onClick={() => onAct("publish")}>Publish</button>}
      {status === "published" && republish && can("cms:approve") && <button className="btn sm primary" onClick={() => onAct("publish")}>Publish changes</button>}
      {status === "published" && can("cms:approve") && <button className="btn sm" onClick={() => onAct("unpublish")}>Unpublish</button>}
    </div>
  );
}
