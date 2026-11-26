(function () {
  "use strict";

  var container = document.querySelector("[data-event-calendar]");
  if (!container) return;

  var grid = container.querySelector("[data-calendar-grid]");
  var status = container.querySelector("[data-calendar-status]");
  var periodLabel = container.querySelector("[data-calendar-period]");
  var view = "month";
  var selectedDate = dateFromKey(container.getAttribute("data-today")) || new Date();
  var requestNumber = 0;
  var weekdayFormatter = new Intl.DateTimeFormat("fr-FR", {
    weekday: "short"
  });
  var longDateFormatter = new Intl.DateTimeFormat("fr-FR", {
    dateStyle: "long"
  });
  var shortDateFormatter = new Intl.DateTimeFormat("fr-FR", {
    day: "numeric",
    month: "short"
  });
  var monthFormatter = new Intl.DateTimeFormat("fr-FR", {
    month: "long",
    year: "numeric"
  });

  function dateFromKey(key) {
    if (!key) return null;
    var parts = key.split("-").map(Number);
    if (parts.length !== 3 || parts.some(function (part) { return !Number.isInteger(part); })) {
      return null;
    }
    return new Date(parts[0], parts[1] - 1, parts[2], 12);
  }

  function dateAtNoon(date) {
    return new Date(date.getFullYear(), date.getMonth(), date.getDate(), 12);
  }

  function addDays(date, count) {
    return new Date(date.getFullYear(), date.getMonth(), date.getDate() + count, 12);
  }

  function dateKey(date) {
    return [
      date.getFullYear(),
      String(date.getMonth() + 1).padStart(2, "0"),
      String(date.getDate()).padStart(2, "0")
    ].join("-");
  }

  function mondayOf(date) {
    var day = date.getDay();
    return addDays(date, -(day === 0 ? 6 : day - 1));
  }

  function getRange() {
    var anchor = dateAtNoon(selectedDate);
    if (view === "day") {
      return { start: anchor, end: addDays(anchor, 1) };
    }
    if (view === "week") {
      var weekStart = mondayOf(anchor);
      return { start: weekStart, end: addDays(weekStart, 7) };
    }
    var monthStart = mondayOf(new Date(anchor.getFullYear(), anchor.getMonth(), 1, 12));
    var monthEnd = mondayOf(new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0, 12));
    return { start: monthStart, end: addDays(monthEnd, 7) };
  }

  function rangeLabel(range) {
    if (view === "day") return longDateFormatter.format(range.start);
    if (view === "month") {
      var label = monthFormatter.format(selectedDate);
      return label.charAt(0).toLocaleUpperCase("fr-FR") + label.slice(1);
    }
    var lastDay = addDays(range.end, -1);
    return shortDateFormatter.format(range.start) + " – " + longDateFormatter.format(lastDay);
  }

  function setText(element, text) {
    element.textContent = text;
  }

  function createDayCell(date, events, isCurrentMonth) {
    var key = dateKey(date);
    var cell = document.createElement("section");
    cell.className = "event-calendar__day";
    if (key === container.getAttribute("data-today")) {
      cell.classList.add("event-calendar__day--today");
    }
    if (view === "month" && !isCurrentMonth) cell.classList.add("event-calendar__day--outside");

    var heading = document.createElement("div");
    heading.className = "event-calendar__day-heading";
    var weekday = document.createElement("span");
    setText(weekday, weekdayFormatter.format(date));
    var dateElement = document.createElement("time");
    dateElement.dateTime = key;
    setText(dateElement, String(date.getDate()));
    heading.appendChild(weekday);
    heading.appendChild(dateElement);
    cell.appendChild(heading);

    var list = document.createElement("ul");
    list.className = "event-calendar__items";
    events.forEach(function (event) {
      if (event.start_day > key || event.end_day < key) return;

      var item = document.createElement("li");
      var link = document.createElement("a");
      link.className = "event-calendar__event";
      if (["draft", "cancelled", "completed"].indexOf(event.status) !== -1) {
        link.classList.add("event-calendar__event--" + event.status);
      }
      link.href = event.url;
      link.title = [event.status_label, event.place].filter(Boolean).join(" · ");

      var time = document.createElement("time");
      var timeLabel;
      if (event.start_day === key && event.end_day === key) {
        timeLabel = event.start_time + " – " + event.end_time;
      } else if (event.start_day === key) {
        timeLabel = "Début " + event.start_time;
      } else if (event.end_day === key) {
        timeLabel = "Fin " + event.end_time;
      } else {
        timeLabel = "En cours";
      }
      setText(time, timeLabel);
      link.appendChild(time);

      var title = document.createElement("strong");
      setText(title, event.title);
      link.appendChild(title);
      if (event.place) {
        var place = document.createElement("small");
        setText(place, event.place);
        link.appendChild(place);
      }
      item.appendChild(link);
      list.appendChild(item);
    });
    cell.appendChild(list);
    return cell;
  }

  function renderCalendar(range, events, truncated) {
    var days = [];
    for (var date = range.start; date < range.end; date = addDays(date, 1)) {
      days.push(date);
    }
    var currentMonth = selectedDate.getMonth();
    var fragment = document.createDocumentFragment();
    days.forEach(function (date) {
      fragment.appendChild(
        createDayCell(date, events, date.getMonth() === currentMonth)
      );
    });
    grid.replaceChildren(fragment);

    if (!events.length) {
      setText(status, "Aucun événement pour cette période.");
    } else {
      setText(
        status,
        events.length + " événement(s) affiché(s)." +
          (truncated ? " La liste est limitée aux 500 premiers événements." : "")
      );
    }
  }

  function loadCalendar() {
    var range = getRange();
    var currentRequest = ++requestNumber;
    setText(periodLabel, rangeLabel(range));
    setText(status, "Chargement du calendrier…");
    grid.replaceChildren();

    var endpoint = new URL(container.getAttribute("data-feed-url"), window.location.origin);
    var params = new URLSearchParams(window.location.search);
    params.set("start", dateKey(range.start));
    params.set("end", dateKey(range.end));
    endpoint.search = params.toString();

    fetch(endpoint.toString(), {
      credentials: "same-origin",
      headers: { Accept: "application/json" }
    })
      .then(function (response) {
        if (!response.ok) {
          return response.json().then(function (data) {
            throw new Error(data.error || "Le calendrier n’a pas pu être chargé.");
          });
        }
        return response.json();
      })
      .then(function (data) {
        if (currentRequest !== requestNumber) return;
        renderCalendar(range, data.events, data.truncated);
      })
      .catch(function (error) {
        if (currentRequest !== requestNumber) return;
        grid.replaceChildren();
        setText(status, error.message || "Le calendrier n’a pas pu être chargé.");
      });
  }

  container.querySelectorAll("[data-calendar-view-button]").forEach(function (button) {
    button.addEventListener("click", function () {
      view = button.getAttribute("data-calendar-view-button");
      container.setAttribute("data-view", view);
      container.querySelectorAll("[data-calendar-view-button]").forEach(function (viewButton) {
        viewButton.setAttribute(
          "aria-pressed",
          String(viewButton === button)
        );
      });
      loadCalendar();
    });
  });

  container.querySelector("[data-calendar-prev]").addEventListener("click", function () {
    if (view === "day") selectedDate = addDays(selectedDate, -1);
    else if (view === "week") selectedDate = addDays(selectedDate, -7);
    else selectedDate = new Date(selectedDate.getFullYear(), selectedDate.getMonth() - 1, 1, 12);
    loadCalendar();
  });

  container.querySelector("[data-calendar-next]").addEventListener("click", function () {
    if (view === "day") selectedDate = addDays(selectedDate, 1);
    else if (view === "week") selectedDate = addDays(selectedDate, 7);
    else selectedDate = new Date(selectedDate.getFullYear(), selectedDate.getMonth() + 1, 1, 12);
    loadCalendar();
  });

  container.querySelector("[data-calendar-today]").addEventListener("click", function () {
    selectedDate = dateFromKey(container.getAttribute("data-today")) || new Date();
    loadCalendar();
  });

  loadCalendar();
})();
