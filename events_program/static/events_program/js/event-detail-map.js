(function () {
  "use strict";

  document.querySelectorAll("[data-event-location-map]").forEach(function (container) {
    var status = container.querySelector("[data-map-status]");
    var canvas = container.querySelector("[data-map-canvas]");
    if (!window.L) {
      status.textContent = "La carte est indisponible. L’adresse de l’événement reste affichée.";
      return;
    }

    var latitude = Number(container.getAttribute("data-latitude"));
    var longitude = Number(container.getAttribute("data-longitude"));
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
      status.textContent = "Les coordonnées de ce lieu ne sont pas valides.";
      return;
    }

    var map = L.map(canvas, {
      scrollWheelZoom: false,
      minZoom: 5,
      maxZoom: 18
    }).setView([latitude, longitude], 14);
    L.tileLayer(container.getAttribute("data-tiles-url"), {
      minZoom: 5,
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'
    }).addTo(map);
    var popup = document.createElement("span");
    popup.textContent = container.getAttribute("data-location-name");
    L.marker([latitude, longitude]).addTo(map).bindPopup(popup);
    status.textContent = "Emplacement du lieu de l’événement.";
  });
})();
