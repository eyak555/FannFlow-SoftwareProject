/* Dossier de presse : n'affiche que les communications et médias de
   l'événement choisi. Simple confort de saisie : le serveur refuse de toute
   façon une sélection d'un autre événement (PressKitForm.clean).
   Une case déjà cochée d'un autre événement reste visible pour que
   l'erreur soit compréhensible et corrigeable. */
(function () {
  "use strict";
  var select = document.querySelector("[data-event-select]");
  var groups = document.querySelectorAll("[data-event-choices]");
  if (!select || !groups.length) return;

  function refresh() {
    var eventId = select.value;
    groups.forEach(function (group) {
      var visible = 0;
      group.querySelectorAll("input[type=checkbox]").forEach(function (box) {
        var item = box.closest("div") || box.parentElement;
        var show = !eventId || box.dataset.event === eventId || box.checked;
        item.hidden = !show;
        if (show) visible += 1;
      });
      var empty = group.parentElement.querySelector("[data-event-choices-empty]");
      if (empty) empty.hidden = visible > 0;
    });
  }

  select.addEventListener("change", refresh);
  refresh();
})();
