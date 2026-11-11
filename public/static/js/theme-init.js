/* Applies appearance preferences before first paint to avoid a flash.
   Signed-in pages carry the user's saved settings (data-prefs="server"); they are cached locally so the
   login page matches the last user's appearance. */
(function () {
  var root = document.documentElement;
  var keys = ["theme", "accent", "electric", "orientation"];
  try {
    if (root.getAttribute("data-prefs") === "server") {
      keys.forEach(function (k) { localStorage.setItem("apex-" + k, root.getAttribute("data-" + k)); });
      return;
    }
    keys.forEach(function (k) {
      var v = localStorage.getItem("apex-" + k);
      if (v) root.setAttribute("data-" + k, v);
    });
    if (!localStorage.getItem("apex-theme")) {
      root.setAttribute("data-theme", window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
    }
  } catch (e) { /* storage unavailable */ }
})();
