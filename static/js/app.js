// Small progressive enhancements. The site works without JavaScript except live refresh.
document.addEventListener("submit", function (event) {
  var form = event.target;
  var message = form.getAttribute("data-confirm");
  if (message && !window.confirm(message)) {
    event.preventDefault();
    return;
  }
  var buttons = form.querySelectorAll("button[type=submit]");
  window.setTimeout(function () {
    buttons.forEach(function (b) { b.disabled = true; });
  }, 0);
});

(function setupDetailsDropdowns() {
  var groups = Array.prototype.slice.call(document.querySelectorAll(".nav-group"));
  if (!groups.length) { return; }

  function closeGroup(group) {
    if (group && group.hasAttribute("open")) {
      group.removeAttribute("open");
    }
  }

  function closeOthers(activeGroup) {
    groups.forEach(function (group) {
      if (group !== activeGroup) {
        closeGroup(group);
      }
    });
  }

  groups.forEach(function (group) {
    group.addEventListener("toggle", function () {
      if (group.open) {
        closeOthers(group);
      }
    });
  });

  document.addEventListener("click", function (event) {
    var withinGroup = event.target.closest(".nav-group");
    var clickedLink = event.target.closest(".nav-group a");

    if (!withinGroup) {
      groups.forEach(closeGroup);
      return;
    }

    if (clickedLink) {
      window.setTimeout(function () {
        closeGroup(withinGroup);
      }, 0);
      return;
    }

    if (event.target.closest(".nav-group summary")) {
      closeOthers(withinGroup);
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") {
      return;
    }
    groups.forEach(closeGroup);
  });
})();

(function pollCollection() {
  var box = document.getElementById("collection-status");
  if (!box || box.getAttribute("data-running") !== "true") { return; }
  var url = box.getAttribute("data-status-url");
  function check() {
    fetch(url, { headers: { "Accept": "application/json" }, credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.running) { window.location.reload(); return; }
        box.textContent = "Collection in progress: " + data.sources_done + " of " + data.sources_total + " sources finished.";
        window.setTimeout(check, 2000);
      })
      .catch(function () { window.setTimeout(check, 4000); });
  }
  window.setTimeout(check, 1500);
})();
