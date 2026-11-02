// Small progressive enhancements. The site works without JavaScript except live refresh.
function submitCollectionAssignment(form) {
  var button = form.querySelector("button[type=submit]");
  var select = form.querySelector("select[name=collection_id]");
  var feedback = document.getElementById("collection-assignment-feedback");
  var assignedList = document.getElementById("assigned-collections-list");
  var originalLabel = button.textContent;
  var processingLabel = form.getAttribute("data-processing-label") || "Saving...";
  button.disabled = true;
  button.textContent = processingLabel;
  feedback.textContent = "";
  feedback.className = "assignment-feedback";

  fetch(form.action, {
    method: "POST",
    body: new FormData(form),
    headers: { "X-Requested-With": "XMLHttpRequest" },
    credentials: "same-origin"
  }).then(function (response) {
    return response.json().catch(function () {
      throw new Error("The server returned an unreadable response.");
    }).then(function (data) {
      if (!response.ok || !data.ok) {
        var failure = new Error(data.message || "The assignment could not be saved.");
        failure.assignmentFailure = true;
        throw failure;
      }
      return data;
    });
  }).then(function (data) {
    var existing = Array.prototype.some.call(assignedList.children, function (item) {
      return item.getAttribute("data-assigned-collection-id") === String(data.collection_id);
    });
    if (!existing) {
      var item = document.createElement("li");
      item.setAttribute("data-assigned-collection-id", data.collection_id);
      item.textContent = data.collection_name;
      assignedList.appendChild(item);
    }
    document.getElementById("no-assigned-collections").hidden = false;
    document.getElementById("no-assigned-collections").textContent = "This article is assigned to the sections shown above.";
    var option = Array.prototype.find.call(select.options, function (entry) {
      return entry.value === String(data.collection_id);
    });
    if (option) { option.remove(); }
    select.value = "";
    feedback.textContent = data.message;
    feedback.className = "assignment-feedback flash flash-success";
    if (select.options.length <= 1) {
      form.hidden = true;
      document.getElementById("no-available-collections").hidden = false;
    }
  }).catch(function (error) {
    feedback.textContent = error.assignmentFailure
      ? error.message
      : "The connection was interrupted. Your selection is still here; try again.";
    feedback.className = "assignment-feedback flash flash-error";
  }).finally(function () {
    button.disabled = false;
    button.textContent = originalLabel;
  });
}

document.addEventListener("submit", function (event) {
  var form = event.target;
  if (form.matches("[data-collection-assignment]")) {
    event.preventDefault();
    submitCollectionAssignment(form);
    return;
  }
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
  var latestRequest = 0;

  function updateSelectionState(category) {
    var controls = Array.prototype.slice.call(page.querySelectorAll("[data-category-select]"));
    controls.forEach(function (control) {
      var selected = control.getAttribute("data-category") === category;
      control.classList.toggle("selected", selected);
      var segment = control.querySelector(".pie-segment");
      if (segment) {
        segment.classList.toggle("selected", selected);
      }
      control.setAttribute("aria-pressed", selected ? "true" : "false");
    });
    page.querySelectorAll(".category-detail").forEach(function (detail) {
      var heading = detail.querySelector("h3");
      detail.classList.toggle("active", Boolean(heading) && heading.textContent.trim() === category);
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
        chartMeta.textContent = details[2].textContent.trim() + " articles · " + details[3].textContent.trim();
      }
    }
  }

  function loadCategory(category) {
    var requestId = ++latestRequest;
    var url = "/category-intelligence?source=dashboard&category=" + encodeURIComponent(category) + "&fragment=1";
    fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" }, credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok) { throw new Error("Category details could not be loaded."); }
        return response.text();
      })
      .then(function (html) {
        if (requestId !== latestRequest) { return; }
        var doc = new DOMParser().parseFromString(html, "text/html");
        var nextSummary = doc.querySelector("#chart-side-summary");
        var selectedPanel = doc.querySelector("#selected-category-panel");
        var relatedPanel = doc.querySelector("#related-articles-panel");
        var currentSummary = page.querySelector("#chart-side-summary");
        if (nextSummary && currentSummary) {
          currentSummary.replaceWith(nextSummary);
        }
        if (selectedPanel) {
          page.querySelector("#selected-category-panel").innerHTML = selectedPanel.innerHTML;
        }
        if (relatedPanel) {
          page.querySelector("#related-articles-panel").innerHTML = relatedPanel.innerHTML;
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
