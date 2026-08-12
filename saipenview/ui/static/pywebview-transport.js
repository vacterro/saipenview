/* PyWebViewTransport — bridges SaiApi to the pywebview `window.pywebview.api`.
 *
 * This is the transport for STANDALONE SAIPENVIEW: the Python backend exposes
 * `Api` as the pywebview `js_api`, and pywebview injects it as
 * `window.pywebview.api`. Readiness follows pywebview's own `pywebviewready`
 * window event.
 *
 * `call(method, args)` maps a SaiApi method onto `window.pywebview.api[method]`
 * with the argument list spread, exactly like the old direct calls.
 */
(function () {
  "use strict";

  function PyWebViewTransport() {
    this._ready = false;
  }

  PyWebViewTransport.prototype.init = function () {
    var self = this;
    if (self._ready) return Promise.resolve();
    return new Promise(function (resolve) {
      if (
        typeof window !== "undefined" &&
        window.pywebview &&
        window.pywebview.api
      ) {
        self._ready = true;
        resolve();
        return;
      }
      window.addEventListener(
        "pywebviewready",
        function () {
          self._ready = true;
          resolve();
        },
        { once: true }
      );
    });
  };

  PyWebViewTransport.prototype.call = function (method, args) {
    if (
      typeof window === "undefined" ||
      !window.pywebview ||
      !window.pywebview.api
    ) {
      return Promise.reject(
        new Error("PyWebViewTransport: pywebview bridge not available")
      );
    }
    var fn = window.pywebview.api[method];
    if (typeof fn !== "function") {
      return Promise.reject(
        new Error("PyWebViewTransport: unknown method " + method)
      );
    }
    try {
      return Promise.resolve(fn.apply(window.pywebview.api, args || []));
    } catch (e) {
      return Promise.reject(e);
    }
  };

  PyWebViewTransport.prototype.name = function () {
    return "pywebview";
  };

  if (typeof window !== "undefined") {
    window.PyWebViewTransport = PyWebViewTransport;
  }
})();
