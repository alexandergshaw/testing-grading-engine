/* Browser client for the /api/v1 grading API. The UI has no grading routes of
   its own - everything below goes through the same public endpoints any other
   app would call. */
(function () {
  "use strict";

  var $ = function (sel) { return document.querySelector(sel); };
  var CHECKS = [];        // [{name, required_params, description}] from /api/v1/checks
  var REQUIRED = {};      // name -> [required params]
  var TARGETLESS = ["run_command", "output_contains"];
  var lastResult = null;  // last /grade response

  // ---- API helpers ----

  function apiHeaders(extra) {
    var headers = extra || {};
    var key = localStorage.getItem("gradingApiKey");
    if (key) headers["X-API-Key"] = key;
    return headers;
  }

  function apiFetch(path, options) {
    return fetch(path, options).then(function (resp) {
      return resp.json().catch(function () { return null; }).then(function (data) {
        if (!resp.ok) {
          var msgs = (data && data.messages) || [resp.status + " " + resp.statusText];
          if (resp.status === 401) $("#key-bar").hidden = false;
          throw msgs;
        }
        return data;
      });
    });
  }

  // ---- view + error plumbing ----

  function showView(name) {
    ["upload", "review", "results"].forEach(function (v) {
      $("#view-" + v).hidden = v !== name;
    });
    clearErrors();
    window.scrollTo(0, 0);
  }

  function showErrors(msgs) {
    var ul = $("#errors");
    ul.innerHTML = "";
    (Array.isArray(msgs) ? msgs : [String(msgs)]).forEach(function (m) {
      var li = document.createElement("li");
      li.textContent = m;
      ul.appendChild(li);
    });
    ul.hidden = false;
    window.scrollTo(0, 0);
  }

  function clearErrors() {
    $("#errors").hidden = true;
  }

  // ---- params helpers (mirror grading/rubric.py semantics) ----

  function parseParams(raw) {
    var out = {}, parts = [], cur = "";
    for (var i = 0; i < (raw || "").length; i++) {
      if (raw[i] === ";" && raw[i - 1] !== "\\") { parts.push(cur); cur = ""; }
      else cur += raw[i];
    }
    parts.push(cur);
    parts.forEach(function (p) {
      var t = p.trim();
      if (!t) return;
      var eq = t.indexOf("=");
      if (eq < 0) return;
      out[t.slice(0, eq).trim()] = t.slice(eq + 1).trim();
    });
    return out;
  }

  function needsSetup(checkType, paramsRaw) {
    if (!REQUIRED.hasOwnProperty(checkType)) return true;
    var params = parseParams(paramsRaw);
    return REQUIRED[checkType].some(function (p) { return !(p in params); });
  }

  // ---- review table ----

  function makeInput(name, value, placeholder, cls) {
    var input = document.createElement("input");
    input.name = name;
    input.value = value || "";
    if (placeholder) input.placeholder = placeholder;
    if (cls) input.className = cls;
    return input;
  }

  function updateRowState(tr) {
    var check = tr.querySelector('[name="check_type"]').value;
    var params = tr.querySelector('[name="params"]');
    var target = tr.querySelector('[name="target"]');
    var req = REQUIRED[check] || [];
    params.placeholder = req.length
      ? req.map(function (p) { return p + "=…"; }).join(";") + " (required)"
      : "key=value;key=value";
    target.placeholder = TARGETLESS.indexOf(check) >= 0
      ? "(not used by this check)"
      : "*.py or main.py";
    tr.classList.toggle("needs-setup", needsSetup(check, params.value));
  }

  function renderReview(rows) {
    var tbody = $("#review-rows");
    tbody.innerHTML = "";
    rows.forEach(function (row) {
      var tr = document.createElement("tr");
      tr.className = "crit";

      var tdName = document.createElement("td");
      tdName.className = "grow";
      tdName.appendChild(makeInput("criterion", row.criterion));
      tr.appendChild(tdName);

      var tdPts = document.createElement("td");
      tdPts.appendChild(makeInput("points", String(Number(row.points)), "10", "narrow"));
      tr.appendChild(tdPts);

      var tdCheck = document.createElement("td");
      var select = document.createElement("select");
      select.name = "check_type";
      var blank = document.createElement("option");
      blank.value = "";
      blank.textContent = "choose…";
      select.appendChild(blank);
      CHECKS.forEach(function (c) {
        var opt = document.createElement("option");
        opt.value = c.name;
        opt.textContent = c.name;
        if (c.name === row.check_type) opt.selected = true;
        select.appendChild(opt);
      });
      tdCheck.appendChild(select);
      tr.appendChild(tdCheck);

      var tdTarget = document.createElement("td");
      tdTarget.appendChild(makeInput("target", row.target));
      tr.appendChild(tdTarget);

      var tdParams = document.createElement("td");
      tdParams.className = "grow";
      tdParams.appendChild(makeInput("params", row.params));
      tr.appendChild(tdParams);

      var tdRule = document.createElement("td");
      tdRule.className = "rule";
      tdRule.textContent = row.rule || "";
      tr.appendChild(tdRule);

      ["change", "input"].forEach(function (ev) {
        tr.addEventListener(ev, function () { updateRowState(tr); });
      });
      tbody.appendChild(tr);
      updateRowState(tr);
    });
    $("#review-summary").textContent =
      rows.length + " criteria parsed deterministically from your paste. Confirm the " +
      "suggested checks, fix highlighted rows, then upload the submissions zip and grade.";
    showView("review");
  }

  function reviewRows() {
    var rows = [];
    document.querySelectorAll("#review-rows tr.crit").forEach(function (tr) {
      var get = function (n) { return tr.querySelector('[name="' + n + '"]').value; };
      rows.push({
        criterion: get("criterion"),
        points: get("points"),
        check_type: get("check_type"),
        target: get("target"),
        params: get("params"),
      });
    });
    return rows;
  }

  // ---- results ----

  function fmt(n) { return String(Number(n)); }

  function renderResults(data) {
    lastResult = data;
    var head = $("#results-head");
    var body = $("#results-body");
    head.innerHTML = "";
    body.innerHTML = "";

    var headRow = document.createElement("tr");
    ["Student"].concat(data.criteria, ["Total", "Possible"]).forEach(function (h) {
      var th = document.createElement("th");
      th.textContent = h;
      headRow.appendChild(th);
    });
    head.appendChild(headRow);

    data.students.forEach(function (s) {
      var tr = document.createElement("tr");
      var tdStudent = document.createElement("td");
      tdStudent.className = "student";
      tdStudent.textContent = s.student;
      tr.appendChild(tdStudent);
      s.criteria.forEach(function (c) {
        var td = document.createElement("td");
        td.className = c.passed ? "pass" : "fail";
        td.title = c.detail;
        td.innerHTML = "";
        td.appendChild(document.createTextNode(fmt(c.points_earned)));
        var of = document.createElement("span");
        of.className = "of";
        of.textContent = "/" + fmt(c.points_possible);
        td.appendChild(of);
        tr.appendChild(td);
      });
      var tdTotal = document.createElement("td");
      tdTotal.className = "total";
      tdTotal.textContent = fmt(s.total);
      tr.appendChild(tdTotal);
      var tdPossible = document.createElement("td");
      tdPossible.className = "possible";
      tdPossible.textContent = fmt(s.possible);
      tr.appendChild(tdPossible);
      body.appendChild(tr);
    });

    var warnings = $("#warnings");
    warnings.innerHTML = "";
    (data.warnings || []).forEach(function (w) {
      var li = document.createElement("li");
      li.textContent = w;
      warnings.appendChild(li);
    });
    warnings.hidden = !(data.warnings || []).length;

    $("#results-summary").textContent =
      data.students.length + " student(s) · " + data.criteria.length + " criteria";
    showView("results");
  }

  function downloadBlob(text, filename, type) {
    var a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type: type }));
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  // ---- grading via the API ----

  function gradeWith(formData, button) {
    button.disabled = true;
    button.textContent = "Grading…";
    apiFetch("/api/v1/grade", { method: "POST", headers: apiHeaders(), body: formData })
      .then(renderResults)
      .catch(showErrors)
      .finally(function () {
        button.disabled = false;
        button.textContent = "Grade";
      });
  }

  // ---- wire up ----

  $("#csv-form").addEventListener("submit", function (e) {
    e.preventDefault();
    clearErrors();
    var fd = new FormData();
    fd.append("submissions", $("#csv-zip").files[0]);
    fd.append("rubric_csv", $("#csv-rubric").files[0]);
    gradeWith(fd, e.target.querySelector("button"));
  });

  $("#paste-form").addEventListener("submit", function (e) {
    e.preventDefault();
    clearErrors();
    apiFetch("/api/v1/rubric/parse", {
      method: "POST",
      headers: apiHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ rubric_text: $("#rubric-text").value }),
    })
      .then(function (data) { renderReview(data.criteria); })
      .catch(showErrors);
  });

  $("#review-grade").addEventListener("click", function () {
    clearErrors();
    var zip = $("#review-zip").files[0];
    if (!zip) { showErrors(["Please choose a submissions zip file."]); return; }
    var fd = new FormData();
    fd.append("submissions", zip);
    fd.append("rubric_json", JSON.stringify(reviewRows()));
    gradeWith(fd, $("#review-grade"));
  });

  $("#dl-rubric").addEventListener("click", function () {
    var rows = [["criterion", "points", "check_type", "target", "params"]];
    reviewRows().forEach(function (r) {
      rows.push([r.criterion, r.points, r.check_type, r.target, r.params]);
    });
    var esc = function (v) { return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
    var csv = rows.map(function (r) { return r.map(esc).join(","); }).join("\n") + "\n";
    downloadBlob(csv, "rubric.csv", "text/csv");
  });

  $("#dl-grades").addEventListener("click", function () {
    if (lastResult) downloadBlob(lastResult.csv, "grades.csv", "text/csv");
  });

  $("#review-back").addEventListener("click", function () { showView("upload"); });
  $("#results-back").addEventListener("click", function () {
    $("#csv-form").reset();
    $("#review-zip").value = "";
    showView("upload");
  });

  $("#save-key").addEventListener("click", function () {
    localStorage.setItem("gradingApiKey", $("#api-key").value.trim());
    $("#key-bar").hidden = true;
    init();
  });

  // dropzone enhancement (filename + drag highlight)
  document.querySelectorAll(".dropzone").forEach(function (zone) {
    var input = zone.querySelector("input");
    input.addEventListener("change", function () {
      if (input.files.length) {
        zone.querySelector(".dz-hint").textContent = input.files[0].name;
        zone.classList.add("filled");
      }
    });
    ["dragenter", "dragover"].forEach(function (ev) {
      zone.addEventListener(ev, function (e) { e.preventDefault(); zone.classList.add("dragover"); });
    });
    ["dragleave", "drop"].forEach(function (ev) {
      zone.addEventListener(ev, function (e) { e.preventDefault(); zone.classList.remove("dragover"); });
    });
    zone.addEventListener("drop", function (e) {
      if (e.dataTransfer.files.length) {
        input.files = e.dataTransfer.files;
        input.dispatchEvent(new Event("change"));
      }
    });
  });

  function init() {
    apiFetch("/api/v1/health", {})
      .then(function (health) {
        if (health.auth_required && !localStorage.getItem("gradingApiKey")) {
          $("#key-bar").hidden = false;
        }
      })
      .catch(function () {});
    apiFetch("/api/v1/checks", { headers: apiHeaders() })
      .then(function (data) {
        CHECKS = data.checks;
        REQUIRED = {};
        CHECKS.forEach(function (c) { REQUIRED[c.name] = c.required_params; });
      })
      .catch(function () {});
  }

  init();
})();
