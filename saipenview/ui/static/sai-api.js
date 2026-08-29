/* SaiApi — stable frontend API facade for SAIPENVIEW.
 *
 * The UI must never know whether it is talking to a pywebview bridge or to a
 * SAIWORK-managed HTTP service. Every backend operation the UI needs is
 * declared here as a named method; each one forwards to the installed
 * transport (`call(method, args)`), so PyWebViewTransport and HttpTransport
 * are interchangeable behind the same surface.
 *
 * Readiness: the facade dispatches a `saiapiready` window event once a
 * transport is installed AND the backend answered (pywebview ready, or the
 * HTTP health/RPC handshake succeeded). UI code listens to `saiapiready`
 * instead of pywebview's own `pywebviewready`.
 *
 * The method list below IS the contract. It mirrors the Python `Api` surface
 * in api.py 1:1 (snake_case preserved so the transport mapping stays a
 * pass-through). Adding a backend method the UI needs means adding it here,
 * then implementing it in both transports if they are not pass-throughs.
 */
(function () {
  "use strict";

  var SAI_API_METHODS = [
    "acknowledge_external_change",
    "add_human_note",
    "browse_folder",
    "clipboard_copy",
    "close_window",
    "collect_outbox",
    "commit_agent_work",
    "delete_untracked_files",
    "get_agent_history",
    "get_agent_output",
    "get_agent_status",
    "get_agent_transcript",
    "get_autostart_enabled",
    "get_changed_roots",
    "get_config",
    "get_diff",
    "get_engines",
    "get_hidden_projects",
    "get_last_agent_transcript",
    "get_linked_worktrees",
    "get_local_drives",
    "get_project_detail",
    "get_projects",
    "get_scan_error_log",
    "get_scan_errors",


    "get_scan_progress",
    "get_status",
    "get_theme_tokens",
    "get_themes",
    "get_wiki_page",
    "get_wiki_pages",
    "hide_project",
    "launch_agent",
    "list_running_agents",
    "maximize_window",
    "minimize_window",
    "move_by",
    "open_editor",
    "open_folder",
    "open_terminal",
    "quick_search",
    "quit",
    "read_file_text",
    "record_manual_work",
    "refresh_known",
    "reorder_ticket",
    "rescan",
    "revert_agent_work",
    "run_command",
    "save_view_config",
    "send_agent_input",
    "set_always_on_top",
    "set_auto_scan",
    "set_autostart_enabled",
    "set_engine_overrides",
    "set_exclude_dirs",
    "set_frameless",
    "set_hotkeys",
    "set_locale",
    "set_scan_roots",
    "set_scan_tuning",
    "set_snap_hotkey",
    "set_sort_order",
    "set_zoom_level",
    "stop_agent",
    "toggle_pin",
    "toggle_ticket_status",
    "unhide_project",
    "update_project_state",
    "write_file_text"
  ];

  function createSaiApi() {
    var transport = null;
    var ready = false;
    var readyListeners = [];

    var api = {
      /* Install the transport that actually talks to the backend. A transport
       * must implement `call(method, args) -> Promise`. */
      setTransport: function (t) {
        if (!t || typeof t.call !== "function") {
          throw new Error("SaiApi: transport must implement call(method, args)");
        }
        transport = t;
      },

      get transport() {
        return transport;
      },

      get ready() {
        return ready;
      },

      /* Subscribe to readiness. Fires immediately if already ready. */
      onReady: function (cb) {
        if (typeof cb !== "function") return;
        if (ready) {
          cb();
        } else {
          readyListeners.push(cb);
        }
      },

      /* Transport/boot calls this once the backend answered. Idempotent. */
      markReady: function () {
        if (ready) return;
        ready = true;
        var pending = readyListeners.splice(0);
        for (var i = 0; i < pending.length; i++) {
          try {
            pending[i]();
          } catch (e) {
            console.error("[SaiApi] onReady listener failed:", e);
          }
        }
        try {
          window.dispatchEvent(new Event("saiapiready"));
        } catch (e) {
          console.error("[SaiApi] saiapiready dispatch failed:", e);
        }
      },

      /* Capability check: is method supported by current transport? */
      supports: function (name) {
        if (SAI_API_METHODS.indexOf(name) === -1) return false;
        if (!transport) return false;
        var desktopOnly = ["get_autostart_enabled","set_autostart_enabled","set_hotkeys","set_snap_hotkey","set_always_on_top","set_frameless","open_folder","open_terminal","open_editor","run_command","clipboard_copy","quit","minimize_window","maximize_window","close_window","restore_window","move_by","browse_folder"];
        try {
          if (transport.name && transport.name() === "http" && desktopOnly.indexOf(name) !== -1) return false;
        } catch (e) { /* ignore */ }
        return true;
      },

      /* Generic RPC fallback — `call(method, ...args)`. The named methods
       * below are the primary surface; this exists for forward compatibility
       * and debugging. */
      call: function (method) {
        if (!transport) {
          return Promise.reject(new Error("SaiApi: no transport installed"));
        }
        var args = Array.prototype.slice.call(arguments, 1);
        return transport.call(method, args);
      }
    };

    for (var i = 0; i < SAI_API_METHODS.length; i++) {
      (function (name) {
        api[name] = function () {
          var args = Array.prototype.slice.call(arguments);
          if (!transport) {
            return Promise.reject(
              new Error("SaiApi: no transport installed for " + name)
            );
          }
          return transport.call(name, args);
        };
      })(SAI_API_METHODS[i]);
    }

    return api;
  }

  if (typeof window !== "undefined") {
    window.SaiApi = createSaiApi();
  }
})();
