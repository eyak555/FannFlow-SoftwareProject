(function () {
  "use strict";

  var packageSelect = document.getElementById("id_package");
  var priceDisplay = document.querySelector("#package-standard-price strong");
  var pricesElement = document.getElementById("sponsorship-package-prices");
  if (!packageSelect || !priceDisplay || !pricesElement) return;

  var prices = JSON.parse(pricesElement.textContent);

  function updateStandardPrice() {
    var price = prices[packageSelect.value];
    priceDisplay.textContent = price ? price + " DT" : "—";
  }

  packageSelect.addEventListener("change", updateStandardPrice);
  updateStandardPrice();
})();
