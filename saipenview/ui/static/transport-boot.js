/* transport-boot — pick the transport, install it on SaiApi, drive readiness.
 *
 * Selection:
 *   - If `window.__SAIWORK_HTTP_CONFIG__` is present, SAIPENVIEW is running as
 *     a SAIWORK-embedded service: use HttpTransport with the loopback origin
 *     and per-launch token SAIWORK injected before the page loaded.
 *   - Otherwise this is standalone SAIPENVIEW: use PyWebViewTransport.
 *
 * The UI itself never branches on this — SaiApi is the only thing the page
 * talks to. This boot file is the single place that knows the difference.
 */
(function () {
  "use strict";

  function boot() {
    var config = window.__SAIWORK_HTTP_CONFIG__;
    /* Fallback for the iframe-in-proxy path: SAIWORK mounts the tab at
     * `/sidecars/saipenview/?sv_base=<proxied base>&sv_token=<per-launch>`.
     * The token already travels in the events URL for SSE, so the boot config
     * doing the same is consistent — both are loopback-only and per-launch. */
    if (!config && window.location && window.location.search) {
      try {
        var params = new URLSearchParams(window.location.search);
        var base = params.get("sv_base");
        var token = params.get("sv_token");
        if (base && token) {
          config = { baseUrl: base, token: token };
        }
      } catch (e) { /* non-URL env; ignore */ }
    }
    var transport;
    if (
      config &&
      typeof config === "object" &&
      config.baseUrl &&
      config.token
    ) {
      transport = new window.HttpTransport({
        baseUrl: config.baseUrl,
        token: config.token
      });
    } else if (window.PyWebViewTransport) {
      transport = new window.PyWebViewTransport();
    } else {
      console.error(
        "SAIPENVIEW: no transport available (no pywebview bridge, no HTTP config)"
      );
      return;
    }

    window.SaiApi.setTransport(transport);
    transport
      .init()
      .then(function () {
        window.SaiApi.markReady();
      })
      .catch(function (err) {
        console.error("SAIPENVIEW: backend transport init failed:", err);
        /* No saiapiready: the page's own error surface (renderErrorRegion /
         * status line) reports the failure. SAIWORK's embedding layer has its
         * own health view; the tab must not pretend it is connected. */
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
