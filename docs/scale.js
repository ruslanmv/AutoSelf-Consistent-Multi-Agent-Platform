(function () {
  const BASE_W = 960;
  const BASE_H = 540;

  function isSlidePage() {
    const style = (document.body && document.body.getAttribute("style")) || "";
    return /width:\s*960px/i.test(style) && /height:\s*540px/i.test(style);
  }

  function computeScale() {
    const vv = window.visualViewport;
    const w = vv ? vv.width : window.innerWidth;
    const h = vv ? vv.height : window.innerHeight;
    // A tiny safety margin to avoid scrollbars due to rounding.
    const margin = 0.98;
    return Math.min(w / BASE_W, h / BASE_H) * margin;
  }

  function applyScale() {
    if (!isSlidePage()) return;
    const scale = computeScale();
    document.documentElement.classList.add("scaled-slide");
    document.documentElement.style.setProperty("--slide-scale", String(scale));
  }

  window.addEventListener("resize", applyScale, { passive: true });
  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", applyScale, { passive: true });
    window.visualViewport.addEventListener("scroll", applyScale, { passive: true });
  }
  document.addEventListener("DOMContentLoaded", applyScale);
})();
