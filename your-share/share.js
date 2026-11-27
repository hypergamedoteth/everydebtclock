/* Debt per person: Treasury close ÷ the official Census estimate. Not a projected population. */
(function () {
  var box = document.getElementById("share-clock");
  var el = document.getElementById("share-num");
  if (!box || !el) return;
  var b = +box.dataset.b, pop = +box.dataset.pop;
  if (!(pop > 0)) return;
  var nf = new Intl.NumberFormat("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2});
  var share = b / pop;
  el.textContent = (share < 0 ? "−$" : "$") + nf.format(Math.abs(share));
})();
