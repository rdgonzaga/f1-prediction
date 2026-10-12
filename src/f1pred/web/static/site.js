document.querySelectorAll("[data-tabs]").forEach(function (list) {
  var tabs = Array.prototype.slice.call(list.querySelectorAll('[role="tab"]'));
  function show(tab) {
    tabs.forEach(function (t) {
      var on = t === tab;
      t.setAttribute("aria-selected", on ? "true" : "false");
      t.tabIndex = on ? 0 : -1;
      document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
    });
  }
  tabs.forEach(function (t) { t.addEventListener("click", function () { show(t); }); });
  if (tabs.length) show(tabs[0]);
});
