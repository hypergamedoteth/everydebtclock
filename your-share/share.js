/* Live per-person share: projected national debt ÷ projected population. */
(function () {
  var box = document.getElementById("share-clock");
  var el = document.getElementById("share-num");
  if (!box || !el) return;
  var b = +box.dataset.b, r = +box.dataset.r, t0 = +box.dataset.t0;
  var pop = +box.dataset.pop, pr = +box.dataset.pr, pt = +box.dataset.pt;
  var nf = new Intl.NumberFormat("en-US", {minimumFractionDigits: 4, maximumFractionDigits: 4});
  function frame() {
    var t = Date.now() / 1000;
    var debt = b + r * (t - t0);
    var people = pop + pr * (t - pt);
    el.textContent = (debt < 0 ? "−$" : "$") + nf.format(Math.abs(debt / people));
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();
