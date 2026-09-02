import React from "react";
import { useEffect, useState } from "react";

/**
 * In-page diagnostic overlay. Activate with `?diag=1` in the URL.
 *
 * Renders two things:
 *   1. A floating panel (top-left) that shows live numbers:
 *      - window.innerWidth / innerHeight
 *      - visualViewport offsetLeft/Top/width/height/scale
 *      - document.documentElement.clientWidth / scrollWidth
 *      - any ancestor element with a non-none transform / filter
 *      - the modal/dialog's bounding rect when one is open
 *   2. A red dashed outline drawn at "0,0 of the visual viewport" so
 *      the user can SEE where the browser thinks the visible area
 *      starts.
 *
 * Lets a user share a screenshot and the developer can read what the
 * BROWSER actually reports vs what the SPA's `position: fixed`
 * elements end up at. Untouchable bug-finding tool when remote
 * debugging isn't available.
 */
export function DiagOverlay(): React.JSX.Element | null {
  const enabled =
    typeof window !== "undefined" &&
    new URLSearchParams(window.location.search).has("diag");

  const [snap, setSnap] = useState(() => probe());
  useEffect(() => {
    if (!enabled) return;
    function tick(): void {
      setSnap(probe());
    }
    const id = window.setInterval(tick, 500);
    window.addEventListener("scroll", tick, true);
    window.addEventListener("resize", tick);
    window.visualViewport?.addEventListener("scroll", tick);
    window.visualViewport?.addEventListener("resize", tick);
    return () => {
      window.clearInterval(id);
      window.removeEventListener("scroll", tick, true);
      window.removeEventListener("resize", tick);
      window.visualViewport?.removeEventListener("scroll", tick);
      window.visualViewport?.removeEventListener("resize", tick);
    };
  }, [enabled]);

  if (!enabled) return null;

  return (
    <>
      {/* Red dashed outline at 0,0 of layout viewport — shows where
          `position: fixed; inset: 0` *should* land. */}
      <div
        aria-hidden
        style={{
          position: "fixed",
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          border: "3px dashed #ff0000",
          pointerEvents: "none",
          zIndex: 999998,
        }}
      />
      {/* Green outline at 0,0 of VISUAL viewport (via visualViewport
          offset). On Android Chrome with pinch zoom, this should
          differ from the red box when zoomed. */}
      <div
        aria-hidden
        style={{
          position: "fixed",
          top: snap.vv.offsetTop,
          left: snap.vv.offsetLeft,
          width: snap.vv.width,
          height: snap.vv.height,
          border: "3px dashed #00ff00",
          pointerEvents: "none",
          zIndex: 999998,
        }}
      />
      {/* Yellow outline = where the OPEN dialog actually lands. */}
      {snap.dialog && (
        <div
          aria-hidden
          style={{
            position: "fixed",
            top: snap.dialog.y,
            left: snap.dialog.x,
            width: snap.dialog.w,
            height: snap.dialog.h,
            border: "3px dashed #ffff00",
            pointerEvents: "none",
            zIndex: 999998,
          }}
        />
      )}
      <pre
        style={{
          position: "fixed",
          top: 8,
          left: 8,
          maxWidth: "94vw",
          maxHeight: "60vh",
          overflow: "auto",
          margin: 0,
          padding: 8,
          background: "rgba(0,0,0,0.85)",
          color: "#0f0",
          fontFamily: "ui-monospace, monospace",
          fontSize: 10,
          lineHeight: 1.2,
          zIndex: 999999,
          pointerEvents: "auto",
        }}
      >
        {JSON.stringify(snap, null, 2)}
      </pre>
    </>
  );
}

interface DialogRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

interface Snap {
  innerW: number;
  innerH: number;
  vv: { offsetLeft: number; offsetTop: number; width: number; height: number; scale: number };
  doc: { clientW: number; scrollW: number; clientH: number; scrollH: number; scrollX: number; scrollY: number };
  dpr: number;
  dialog: DialogRect | null;
  transformAncestors: number;
}

function probe(): Snap {
  const vv = window.visualViewport;
  let dialog: DialogRect | null = null;
  const dlg = document.querySelector('[role="dialog"]');
  if (dlg) {
    const r = (dlg as HTMLElement).getBoundingClientRect();
    dialog = {
      x: Math.round(r.x),
      y: Math.round(r.y),
      w: Math.round(r.width),
      h: Math.round(r.height),
    };
  }
  // Count ancestors of the body that have transform/filter/perspective
  // set (these change the containing block for fixed children).
  let transformAncestors = 0;
  for (const el of document.body.querySelectorAll("*")) {
    const cs = window.getComputedStyle(el as HTMLElement);
    if (cs.transform !== "none" || cs.filter !== "none" || cs.perspective !== "none") {
      transformAncestors += 1;
    }
  }
  return {
    innerW: window.innerWidth,
    innerH: window.innerHeight,
    vv: {
      offsetLeft: vv ? Math.round(vv.offsetLeft) : 0,
      offsetTop: vv ? Math.round(vv.offsetTop) : 0,
      width: vv ? Math.round(vv.width) : 0,
      height: vv ? Math.round(vv.height) : 0,
      scale: vv ? +vv.scale.toFixed(2) : 1,
    },
    doc: {
      clientW: document.documentElement.clientWidth,
      scrollW: document.documentElement.scrollWidth,
      clientH: document.documentElement.clientHeight,
      scrollH: document.documentElement.scrollHeight,
      scrollX: Math.round(window.scrollX),
      scrollY: Math.round(window.scrollY),
    },
    dpr: window.devicePixelRatio,
    dialog,
    transformAncestors,
  };
}
