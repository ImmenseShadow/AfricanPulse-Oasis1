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

(function setupCategoryBars() {
  var bars = Array.prototype.slice.call(document.querySelectorAll(".category-bar-fill"));
  bars.forEach(function (bar) {
    var width = parseFloat(bar.getAttribute("data-width"));
    if (!Number.isNaN(width)) {
      bar.style.width = width + "%";
    }
  });
})();

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

(function setupCategoryIntelligence() {
  var page = document.querySelector("[data-category-intelligence-page]");
  if (!page) { return; }

  function updateSelectionState(category) {
    var controls = Array.prototype.slice.call(document.querySelectorAll("[data-category-select]"));
    controls.forEach(function (control) {
      var selected = control.getAttribute("data-category") === category;
      control.classList.toggle("selected", selected);
      var circle = control.querySelector("circle");
      if (circle) {
        circle.classList.toggle("selected", selected);
      }
      if (control.tagName === "BUTTON") {
        control.setAttribute("aria-pressed", selected ? "true" : "false");
      }
      if (control.tagName === "G") {
        control.setAttribute("aria-pressed", selected ? "true" : "false");
      }
    });
    var chartLabel = document.getElementById("selected-chart-label");
    var chartMeta = document.getElementById("selected-chart-meta");
    if (chartLabel) {
      chartLabel.textContent = category;
    }
    var selectedPanel = document.getElementById("selected-category-panel");
    if (chartMeta && selectedPanel) {
      var details = selectedPanel.querySelectorAll("dd");
      if (details.length >= 4) {
        chartMeta.textContent = details[2].textContent.trim() + " articles • " + details[3].textContent.trim();
      }
    }
  }

  function loadCategory(category) {
    var url = "/category-intelligence?source=dashboard&category=" + encodeURIComponent(category) + "&fragment=1";
    fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" }, credentials: "same-origin" })
      .then(function (response) { return response.text(); })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, "text/html");
        var selectedPanel = doc.querySelector("#selected-category-panel");
        var relatedPanel = doc.querySelector("#related-articles-panel");
        if (selectedPanel) {
          document.getElementById("selected-category-panel").innerHTML = selectedPanel.innerHTML;
        }
        if (relatedPanel) {
          document.getElementById("related-articles-panel").innerHTML = relatedPanel.innerHTML;
        }
        updateSelectionState(category);
      })
      .catch(function () {
        return;
      });
  }

  page.querySelectorAll("[data-category-select]").forEach(function (control) {
    control.addEventListener("click", function (event) {
      event.preventDefault();
      var category = control.getAttribute("data-category");
      if (!category) { return; }
      loadCategory(category);
    });

    control.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        control.click();
      }
    });
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
