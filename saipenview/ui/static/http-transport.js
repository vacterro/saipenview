/* HttpTransport — bridges SaiApi to the SAIPENVIEW headless service.
 *
 * Used when SAIWORK embeds SAIPENVIEW: the Python backend runs in `--service`
 * mode on 127.0.0.1 and the page talks to it over HTTP. The transport is
 * configured with the loopback origin and the per-launch session token that
 * SAIWORK's SaipenViewServiceManager hands over at mount time.
 *
 * Contract surface (kept deliberately small):
 *   GET  /health          -> { ok: true, version, service }
 *   POST /api/rpc         -> { method, args }  -> { ok, result } | { ok: false, error }
 *   GET  /api/events      -> SSE stream of backend push events
 *
 * All RPC requests carry `Authorization: Bearer <token>`; the service rejects
 * missing/bad tokens before touching the allowlisted handler.
 *
 * Readiness: init() probes /health, then issues a no-op RPC (`get_status`) so
 * `saiapiready` only fires when the API layer itself answers, not merely when
 * the HTTP listener is up.
 */
(function () {
  "use strict";

  function HttpTransport(options) {
    options = options || {};
    this.baseUrl = (options.baseUrl || "").replace(/\/+$/, "");
    this.token = options.token || "";
  }

  HttpTransport.prototype.init = function () {
    var self = this;
    if (self._ready) return Promise.resolve();
    if (!self.baseUrl) {
      return Promise.reject(
        new Error("HttpTransport: no baseUrl configured")
      );
    }
    return self._rpc("get_status", []).then(
      function () {
        self._ready = true;
        self._openEventStream();
      },
      function (err) {
        self._ready = false;
        throw err;
      }
    );
  };

  HttpTransport.prototype.call = function (method, args) {
    if (!this._ready && method !== "get_status") {
      return Promise.reject(
        new Error("HttpTransport: backend not ready for " + method)
      );
    }
    return this._rpc(method, args || []);
  };

  HttpTransport.prototype._rpc = function (method, args) {
    var self = this;
    return fetch(self.baseUrl + "/api/rpc", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        /* Deliberately NOT `Authorization: Bearer`: SAIWORK's SideCar proxy
         * strips the authorization header before forwarding (the loopback
         * service must still authenticate). X-Saipenview-Token passes
         * through the proxy untouched. */
        "X-Saipenview-Token": self.token
      },
      body: JSON.stringify({ method: method, args: args })
    })
      .then(function (response) {
        if (response.status === 401 || response.status === 403) {
          throw new Error(
            "HttpTransport: rejected by backend (bad or missing token)"
          );
        }
        return response.json().then(function (body) {
          if (!body || body.ok === false) {
            throw new Error(
              (body && body.error) || ("RPC failed for " + method)
            );
          }
          return body.result;
        });
      });
  };

  /* Backend push events (file changed, visibility, ...) arrive as Server-Sent
   * Events. Each named event is dispatched to the same window callbacks the
   * pywebview evaluate_js path used, so the page behaves identically under
   * either transport. */
  HttpTransport.prototype._openEventStream = function () {
    var self = this;
    if (typeof EventSource === "undefined") return;
    var source = new EventSource(self.baseUrl + "/api/events?token=" + encodeURIComponent(self.token));
    self._eventSource = source;
    source.addEventListener("message", function (event) {
      var data;
      try {
        data = JSON.parse(event.data);
      } catch (e) {
        return;
      }
      if (!data || !data.event) return;
      if (data.event === "file.changed") {
        if (window.onSaipenFileChanged) {
          window.onSaipenFileChanged(data.root, data.file, data.origin);
        }
      } else if (data.event === "visibility") {
        if (window.__saipenSetVisible) {
          window.__saipenSetVisible(!!data.visible);
        }
      }
    });
    source.onerror = function () {
      /* W2-005: do NOT close on transient errors -- allow EventSource native
       * reconnect. Only close on explicit transport.close(). */
    };
    source.addEventListener("resync_required", function () {
      /* W2-005: server buffer overflowed -- fetch authoritative state. */
      if (window.SaiApi && typeof window.SaiApi.refresh_known === "function") {
        window.SaiApi.refresh_known().then(function (projects) {
          if (projects) window.render(projects, true);
        });
      }
    });
  };

  HttpTransport.prototype.name = function () {
    return "http";
  };

  HttpTransport.prototype.close = function () {
    if (this._eventSource) {
      try {
        this._eventSource.close();
      } catch (e) { /* ignore */ }
      this._eventSource = null;
    }
  };

  if (typeof window !== "undefined") {
    window.HttpTransport = HttpTransport;
  }
})();
