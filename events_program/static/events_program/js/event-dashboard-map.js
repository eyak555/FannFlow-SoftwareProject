(function () {
  "use strict";

  var container = document.querySelector("[data-dashboard-event-map]");
  if (!container) return;

  var status = container.querySelector("[data-map-status]");
  var canvas = container.querySelector("[data-map-canvas]");
  if (!window.L) {
    status.textContent = "La carte est indisponible. Les statistiques restent consultables.";
    return;
  }

  var dataElement = document.getElementById("event-dashboard-map-points");
  var points;
  try {
    points = dataElement ? JSON.parse(dataElement.textContent) : [];
  } catch (error) {
    status.textContent = "Les emplacements des événements n’ont pas pu être lus.";
    return;
  }

  var map = L.map(canvas, {
    maxBounds: L.latLngBounds([30, 7], [37.6, 11.7]),
    maxBoundsViscosity: 1,
    minZoom: 5,
    maxZoom: 18,
    scrollWheelZoom: false
  }).setView([34, 9.5], 6);
  L.tileLayer(container.getAttribute("data-tiles-url"), {
    minZoom: 5,
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'
  }).addTo(map);

  var markers = [];
  points.forEach(function (point) {
    var latitude = Number(point.latitude);
    var longitude = Number(point.longitude);
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return;

    var marker = L.marker([latitude, longitude]).addTo(map);
    var popup = document.createElement("div");
    var link = document.createElement("a");
    link.href = point.url;
    link.textContent = point.title;
    popup.appendChild(link);
    var place = document.createElement("p");
    place.textContent = [point.place, point.start].filter(Boolean).join(" · ");
    popup.appendChild(place);
    marker.bindPopup(popup);
    markers.push(marker);
  });

  if (markers.length) {
    var markerGroup = L.featureGroup(markers);
    map.fitBounds(markerGroup.getBounds().pad(0.15), { maxZoom: 12 });
    status.textContent = markers.length + " événement(s) géolocalisé(s) affiché(s).";
  } else {
    status.textContent = "Aucun événement publié à venir avec des coordonnées dans la sélection actuelle.";
  }
})();
