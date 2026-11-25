/* FannFlow — interactions d'interface (aucune logique métier). */
(function () {
  "use strict";

  function icons() {
    if (window.lucide && typeof window.lucide.createIcons === "function") {
      window.lucide.createIcons({ attrs: { "stroke-width": 1.75 } });
    }
  }

  /* --- Navigation mobile (front-office) --- */
  function setupMobileNav() {
    var toggle = document.querySelector("[data-nav-toggle]");
    var nav = document.querySelector("[data-nav]");
    if (!toggle || !nav) return;
    toggle.addEventListener("click", function () {
      var open = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", String(!open));
      nav.classList.toggle("is-open", !open);
    });
  }

  /* --- Menus déroulants (clavier : Entrée, Échap, flèches) --- */
  function setupDropdowns() {
    var dropdowns = document.querySelectorAll("[data-dropdown]");
    function closeAll(except) {
      dropdowns.forEach(function (dd) {
        if (dd === except) return;
        dd.classList.remove("is-open");
        var t = dd.querySelector("[data-dropdown-toggle]");
        if (t) t.setAttribute("aria-expanded", "false");
      });
    }
    dropdowns.forEach(function (dd) {
      var toggle = dd.querySelector("[data-dropdown-toggle]");
      var items = function () { return dd.querySelectorAll("a[role=menuitem]"); };
      toggle.addEventListener("click", function (event) {
        event.stopPropagation();
        var open = !dd.classList.contains("is-open");
        closeAll(dd);
        dd.classList.toggle("is-open", open);
        toggle.setAttribute("aria-expanded", String(open));
      });
      dd.addEventListener("keydown", function (event) {
        var list = Array.prototype.slice.call(items());
        var index = list.indexOf(document.activeElement);
        if (event.key === "Escape") {
          closeAll();
          toggle.focus();
        } else if (event.key === "ArrowDown") {
          event.preventDefault();
          if (!dd.classList.contains("is-open")) toggle.click();
          (list[index + 1] || list[0]).focus();
        } else if (event.key === "ArrowUp") {
          event.preventDefault();
          (list[index - 1] || list[list.length - 1]).focus();
        }
      });
    });
    document.addEventListener("click", function () { closeAll(); });
  }

  /* --- Barre latérale (back-office, mobile) --- */
  function setupSidebar() {
    var toggle = document.querySelector("[data-sidebar-toggle]");
    var sidebar = document.querySelector("[data-sidebar]");
    var backdrop = document.querySelector("[data-sidebar-close]");
    if (!toggle || !sidebar) return;
    function set(open) {
      sidebar.classList.toggle("is-open", open);
      toggle.setAttribute("aria-expanded", String(open));
      if (backdrop) backdrop.hidden = !open;
    }
    toggle.addEventListener("click", function () { set(!sidebar.classList.contains("is-open")); });
    if (backdrop) backdrop.addEventListener("click", function () { set(false); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") set(false); });
  }

  /* --- Apparition douce des sections --- */
  function setupReveal() {
    var nodes = document.querySelectorAll("[data-reveal]");
    if (!nodes.length) return;
    var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce || !("IntersectionObserver" in window)) {
      nodes.forEach(function (n) { n.classList.add("is-visible"); });
      return;
    }
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    }, { rootMargin: "0px 0px -10% 0px" });
    nodes.forEach(function (n) { observer.observe(n); });
  }

  /* --- Graphiques (Chart.js) avec états chargement / vide / erreur --- */
  var PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"];

  function renderCharts() {
    var holders = document.querySelectorAll("[data-chart]");
    if (!holders.length) return;
    holders.forEach(function (holder) {
      var source = document.getElementById(holder.getAttribute("data-chart-source"));
      var state = holder.querySelector("[data-chart-state]");
      var data = [];
      try { data = source ? JSON.parse(source.textContent) : []; } catch (e) { data = null; }

      function show(kind, text) {
        holder.setAttribute("data-state", kind);
        if (state) state.textContent = text || "";
      }
      if (data === null) return show("error", "Les données du graphique sont illisibles.");
      var total = data.reduce(function (s, d) { return s + (Number(d.value) || 0); }, 0);
      if (!data.length || total === 0) return show("empty", holder.getAttribute("data-empty") || "Aucune donnée pour le moment.");
      if (!window.Chart) return show("error", "Graphique indisponible (bibliothèque non chargée). Consultez le tableau de données.");

      var canvas = holder.querySelector("canvas");
      var type = holder.getAttribute("data-chart");
      var labels = data.map(function (d) { return d.label; });
      var values = data.map(function (d) { return d.value; });
      // Une couleur fournie par le serveur (ex. statut) prime sur l'ordre de la palette.
      var colors = data.map(function (d, i) { return d.color || PALETTE[i % PALETTE.length]; });
      var isPie = type === "doughnut";
      var styles = getComputedStyle(document.documentElement);
      var ink = styles.getPropertyValue("--ink-2").trim() || "#52606d";
      var grid = styles.getPropertyValue("--line").trim() || "#e6ebf0";
      var unit = holder.getAttribute("data-unit") || "";

      try {
        new window.Chart(canvas, {
          type: type,
          data: {
            labels: labels,
            datasets: [{
              label: holder.getAttribute("data-label") || "",
              data: values,
              backgroundColor: isPie ? colors : (type === "line" ? "rgba(42,120,214,.10)" : PALETTE[0]),
              borderColor: isPie ? "#ffffff" : PALETTE[0],
              borderWidth: isPie ? 2 : 2,
              borderRadius: type === "bar" ? 4 : 0,
              maxBarThickness: 34,
              fill: type === "line",
              tension: 0.35,
              pointRadius: 4,
              pointHoverRadius: 6,
              pointBackgroundColor: "#ffffff",
              pointBorderWidth: 2,
            }],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: isPie ? "68%" : undefined,
            interaction: { mode: isPie ? "nearest" : "index", intersect: false },
            plugins: {
              legend: { display: isPie, position: "bottom", labels: { color: ink, boxWidth: 10, boxHeight: 10, usePointStyle: true, padding: 14, font: { family: "Inter", size: 12 } } },
              tooltip: {
                backgroundColor: "#13243b", padding: 10, cornerRadius: 8, titleFont: { family: "Inter", weight: "600" }, bodyFont: { family: "Inter" },
                callbacks: { label: function (ctx) { return " " + (ctx.label && isPie ? ctx.label + " : " : "") + ctx.formattedValue + (unit ? " " + unit : ""); } },
              },
            },
            scales: isPie ? {} : {
              x: { grid: { display: false }, border: { color: grid }, ticks: { color: ink, font: { family: "Inter", size: 11 } } },
              y: { beginAtZero: true, grid: { color: grid }, border: { display: false }, ticks: { color: ink, precision: 0, font: { family: "Inter", size: 11 } } },
            },
          },
        });
        show("ready");
      } catch (err) {
        show("error", "Impossible d’afficher ce graphique.");
      }
    });
  }

  /* --- Fenêtres modales (<dialog>) : « Mon profil » --- */
  function setupDialogs() {
    document.querySelectorAll("[data-dialog-open]").forEach(function (trigger) {
      var dialog = document.getElementById(trigger.getAttribute("data-dialog-open"));
      if (!dialog || typeof dialog.showModal !== "function") return; // le lien reste utilisable
      trigger.addEventListener("click", function (event) {
        event.preventDefault();
        dialog.showModal();
        var first = dialog.querySelector("[aria-selected=true]");
        if (first) first.focus();
      });
      dialog.addEventListener("click", function (event) {
        if (event.target === dialog) dialog.close(); // clic sur le fond
      });
      dialog.addEventListener("close", function () { trigger.focus(); });
    });
    document.querySelectorAll("[data-dialog-close]").forEach(function (button) {
      button.addEventListener("click", function () { button.closest("dialog").close(); });
    });
  }

  /* --- Onglets accessibles (flèches gauche/droite) --- */
  function setupTabs() {
    document.querySelectorAll("[data-tabs]").forEach(function (root) {
      var tabs = Array.prototype.slice.call(root.querySelectorAll("[role=tab]"));
      function select(tab) {
        tabs.forEach(function (t) {
          var on = t === tab;
          t.setAttribute("aria-selected", String(on));
          t.tabIndex = on ? 0 : -1;
          var panel = document.getElementById(t.getAttribute("aria-controls"));
          if (panel) panel.hidden = !on;
        });
      }
      tabs.forEach(function (tab, i) {
        tab.tabIndex = tab.getAttribute("aria-selected") === "true" ? 0 : -1;
        tab.addEventListener("click", function () { select(tab); });
        tab.addEventListener("keydown", function (e) {
          var next = e.key === "ArrowRight" ? tabs[(i + 1) % tabs.length] : e.key === "ArrowLeft" ? tabs[(i - 1 + tabs.length) % tabs.length] : null;
          if (next) { e.preventDefault(); select(next); next.focus(); }
        });
      });
    });
  }

  /* --- Sélecteurs de fichiers : aperçu, nom, taille (photo de profil) --- */
  var MAX_UPLOAD = 2 * 1024 * 1024; // même limite que le modèle (2 Mo)

  function setupFileInputs() {
    document.querySelectorAll('input[type="file"]').forEach(function (input) {
      var preview = document.createElement("div");
      preview.className = "file-preview";
      preview.hidden = true;
      preview.setAttribute("aria-live", "polite");
      input.insertAdjacentElement("afterend", preview);

      input.addEventListener("change", function () {
        var file = input.files && input.files[0];
        preview.innerHTML = "";
        preview.hidden = !file;
        if (!file) return;
        var size = file.size < 1048576 ? Math.max(1, Math.round(file.size / 1024)) + " Ko" : (file.size / 1048576).toFixed(1) + " Mo";
        var tooBig = file.size > MAX_UPLOAD;
        var isImage = /^image\//.test(file.type);
        if (isImage) {
          var img = new Image();
          img.alt = "";
          img.src = URL.createObjectURL(file);
          preview.appendChild(img);
          // Aperçu immédiat dans l'en-tête de la fenêtre « Mon profil ».
          var avatar = input.closest(".acct") && input.closest(".acct").querySelector(".acct__head .avatar");
          if (avatar && !tooBig) {
            avatar.innerHTML = "";
            var copy = new Image();
            copy.alt = "";
            copy.src = img.src;
            avatar.appendChild(copy);
          }
        }
        var text = document.createElement("span");
        var name = document.createElement("strong");
        var note = document.createElement("small");
        name.textContent = file.name;
        note.textContent = tooBig ? size + " — trop lourd (2 Mo maximum)" : size + " — prêt, cliquez sur Enregistrer";
        text.appendChild(name);
        text.appendChild(note);
        preview.appendChild(text);
        preview.classList.toggle("is-error", tooBig);
      });
    });
  }

  function start() {
    icons();
    setupFileInputs();
    setupDialogs();
    setupTabs();
    setupMobileNav();
    setupDropdowns();
    setupSidebar();
    setupReveal();
    renderCharts();
  }

  // Les scripts "defer" (Lucide, Chart.js) sont tous exécutés avant DOMContentLoaded.
  if (document.readyState === "complete") {
    start();
  } else {
    document.addEventListener("DOMContentLoaded", start);
  }
})();
