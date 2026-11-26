(function () {
  "use strict";

  var root = document.querySelector("[data-venue-map]");
  if (!root) return;

  var status = root.querySelector("[data-map-status]");
  var canvas = root.querySelector("#event-location-map");
  if (!window.L) {
    status.textContent = "La carte n’a pas pu être chargée. Vous pouvez toujours enregistrer le lieu manuellement.";
    return;
  }

  var latitudeInput = document.getElementById("id_selected_latitude");
  var longitudeInput = document.getElementById("id_selected_longitude");
  var tokenInput = document.getElementById("id_location_token");
  var venueSelect = document.getElementById("id_venue");
  var locationInput = document.getElementById("id_location");
  var addressInput = document.getElementById("id_new_venue_address");
  var cityInput = document.getElementById("id_new_venue_city");
  var queryInput = root.querySelector("[data-geocode-query]");
  var searchButton = root.querySelector("[data-geocode-search]");
  var results = root.querySelector("[data-geocode-results]");
  var clearButton = root.querySelector("[data-map-clear]");
  var bounds = L.latLngBounds([30, 7], [37.6, 11.7]);
  var map = L.map(canvas, {
    maxBounds: bounds,
    maxBoundsViscosity: 1,
    minZoom: 5,
    maxZoom: 18
  }).setView([34, 9.5], 6);
  var marker = null;

  L.tileLayer(root.getAttribute("data-tiles-url"), {
    minZoom: 5,
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'
  }).addTo(map);

  function setStatus(message, isError) {
    status.textContent = message;
    status.classList.toggle("is-error", Boolean(isError));
  }

  function clearCustomCoordinates() {
    latitudeInput.value = "";
    longitudeInput.value = "";
    tokenInput.value = "";
  }

  function removeMarker() {
    if (marker) {
      map.removeLayer(marker);
      marker = null;
    }
  }

  function selectedVenueOption() {
    if (!venueSelect || !venueSelect.value) return null;
    return venueSelect.options[venueSelect.selectedIndex];
  }

  function showVenue(venue, shouldFit) {
    removeMarker();
    clearCustomCoordinates();
    if (venue && venue.value) {
      locationInput.value = venue.getAttribute("data-venue-name") || locationInput.value;
    }
    if (!venue || !venue.getAttribute("data-latitude") || !venue.getAttribute("data-longitude")) {
      setStatus("Ce lieu n’a pas encore de coordonnées. Recherchez une position ou conservez le lieu textuel.");
      return;
    }
    var lat = Number(venue.getAttribute("data-latitude"));
    var lon = Number(venue.getAttribute("data-longitude"));
    marker = L.marker([lat, lon]).addTo(map);
    if (shouldFit) map.setView([lat, lon], 15);
    setStatus(
      (venue.getAttribute("data-venue-name") || "Lieu enregistré") +
      " — " + (venue.getAttribute("data-venue-city") || "ville non précisée") +
      ". Le lieu enregistré ne sera pas modifié."
    );
  }

  function showResults(items) {
    results.replaceChildren();
    if (!items.length) {
      results.hidden = false;
      var empty = document.createElement("li");
      empty.textContent = "Aucun lieu trouvé en Tunisie. Vous pouvez saisir le lieu manuellement.";
      results.appendChild(empty);
      return;
    }
    items.forEach(function (item) {
      var li = document.createElement("li");
      var button = document.createElement("button");
      button.type = "button";
      button.textContent = item.label;
      button.addEventListener("click", function () {
        applyVerifiedLocation(item);
        results.hidden = true;
      });
      li.appendChild(button);
      results.appendChild(li);
    });
    results.hidden = false;
  }

  function applyVerifiedLocation(location) {
    venueSelect.value = "";
    locationInput.value = location.name || location.label.split(",")[0];
    addressInput.value = location.address || location.label.slice(0, 255);
    cityInput.value = location.city || "";
    latitudeInput.value = Number(location.latitude).toFixed(6);
    longitudeInput.value = Number(location.longitude).toFixed(6);
    tokenInput.value = location.token;
    removeMarker();
    marker = L.marker([Number(location.latitude), Number(location.longitude)], {
      draggable: true
    }).addTo(map);
    map.setView(marker.getLatLng(), 15);
    marker.on("dragend", verifyDraggedMarker);
    setStatus(location.label + " — position vérifiée en Tunisie.");
  }

  function requestJson(url) {
    return fetch(url, {
      headers: { "Accept": "application/json" },
      credentials: "same-origin"
    }).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok) {
          var error = new Error(data.error || "La recherche a échoué.");
          error.status = response.status;
          throw error;
        }
        return data;
      });
    });
  }

  function reverseLookup(lat, lon) {
    var url = root.getAttribute("data-geocode-url") +
      "?reverse=1&lat=" + encodeURIComponent(lat.toFixed(6)) +
      "&lon=" + encodeURIComponent(lon.toFixed(6));
    return requestJson(url);
  }

  function verifyDraggedMarker() {
    var point = marker.getLatLng();
    tokenInput.value = "";
    setStatus("Vérification de la nouvelle position…");
    reverseLookup(point.lat, point.lng).then(function (location) {
      applyVerifiedLocation(location);
    }).catch(function (error) {
      removeMarker();
      clearCustomCoordinates();
      addressInput.value = "";
      cityInput.value = "";
      setStatus(error.message + " Vous pouvez conserver un lieu textuel sans coordonnées.", true);
    });
  }

  function verifyMapClick(point) {
    if (!bounds.contains(point)) {
      setStatus("Choisissez une position dans la zone de la Tunisie.", true);
      return;
    }
    venueSelect.value = "";
    clearCustomCoordinates();
    removeMarker();
    addressInput.value = "";
    cityInput.value = "";
    setStatus("Vérification de la position en Tunisie…");
    reverseLookup(point.lat, point.lng).then(function (location) {
      applyVerifiedLocation(location);
    }).catch(function (error) {
      setStatus(error.message + " Vous pouvez conserver un lieu textuel sans coordonnées.", true);
    });
  }

  searchButton.addEventListener("click", function () {
    var query = queryInput.value.trim();
    if (!query) {
      setStatus("Saisissez une ville ou une adresse à rechercher.", true);
      return;
    }
    searchButton.disabled = true;
    setStatus("Recherche en cours…");
    var url = root.getAttribute("data-geocode-url") + "?q=" + encodeURIComponent(query);
    requestJson(url).then(function (data) {
      showResults(data.results || []);
      setStatus(data.results && data.results.length ? "Choisissez une adresse dans les résultats." : "Aucun résultat.");
    }).catch(function (error) {
      setStatus(error.message + " Vous pouvez enregistrer le lieu sans coordonnées.", true);
    }).then(function () {
      searchButton.disabled = false;
    });
  });

  queryInput.addEventListener("keydown", function (event) {
    if (event.key === "Enter") {
      event.preventDefault();
      searchButton.click();
    }
  });

  clearButton.addEventListener("click", function () {
    venueSelect.value = "";
    clearCustomCoordinates();
    removeMarker();
    addressInput.value = "";
    cityInput.value = "";
    results.hidden = true;
    setStatus("Position effacée. Le lieu textuel peut être enregistré sans coordonnées.");
  });

  venueSelect.addEventListener("change", function () {
    var option = selectedVenueOption();
    addressInput.value = option ? option.getAttribute("data-venue-address") || "" : "";
    cityInput.value = option ? option.getAttribute("data-venue-city") || "" : "";
    showVenue(option, true);
  });

  map.on("click", function (event) {
    verifyMapClick(event.latlng);
  });

  var initialVenue = selectedVenueOption();
  if (latitudeInput.value && longitudeInput.value && tokenInput.value) {
    applyVerifiedLocation({
      latitude: latitudeInput.value,
      longitude: longitudeInput.value,
      token: tokenInput.value,
      name: locationInput.value,
      label: addressInput.value,
      address: addressInput.value,
      city: cityInput.value
    });
  } else if (initialVenue && initialVenue.value) {
    showVenue(initialVenue, true);
  } else {
    setStatus("Cliquez sur la carte ou recherchez une adresse. Les coordonnées sont facultatives.");
  }
})();
