(function () {
  var data = window.PLT || {};

  // Hero demo: cycle the translated line through the game languages.
  var langEl = document.getElementById("demo-lang");
  var lineEl = document.getElementById("demo-line");
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (langEl && lineEl && data.demo && data.demo.length > 1 && !reduce) {
    var i = 0;
    setInterval(function () {
      if (document.hidden) return;
      i = (i + 1) % data.demo.length;
      langEl.textContent = data.demo[i][0] + ":";
      lineEl.innerHTML = '"' + data.demo[i][1] + '"';
      lineEl.parentNode.classList.remove("swap");
      void lineEl.offsetWidth;
      lineEl.parentNode.classList.add("swap");
    }, 2600);
  }

  // Suggest a page in the browser's language. Never redirect.
  var bar = document.getElementById("suggest");
  var dismissed = false;
  try { dismissed = localStorage.getItem("plt-suggest-dismissed") === "1"; } catch (e) {}
  if (bar && data.langs && !dismissed) {
    var prefs = navigator.languages || [navigator.language || ""];
    var match = null;
    for (var p = 0; p < prefs.length && !match; p++) {
      var want = String(prefs[p]).toLowerCase();
      for (var k = 0; k < data.langs.length; k++) {
        var tag = data.langs[k].tag.toLowerCase();
        if (want === tag || want.split("-")[0] === tag.split("-")[0]) { match = data.langs[k]; break; }
      }
    }
    if (match && match.tag !== data.here && match.text) {
      var link = document.getElementById("suggest-link");
      link.href = match.href;
      link.textContent = match.text;
      link.lang = match.tag;
      bar.hidden = false;
      document.getElementById("suggest-close").addEventListener("click", function () {
        bar.hidden = true;
        try { localStorage.setItem("plt-suggest-dismissed", "1"); } catch (e) {}
      });
    }
  }

  // Screenshot lightbox.
  var box = document.getElementById("lightbox");
  if (box) {
    var img = box.querySelector("img");
    document.querySelectorAll(".zoom").forEach(function (btn) {
      btn.addEventListener("click", function () {
        img.src = btn.getAttribute("data-full");
        img.alt = btn.querySelector("img").alt;
        box.hidden = false;
      });
    });
    box.addEventListener("click", function () { box.hidden = true; });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") box.hidden = true; });
  }

  // Close the language menu when clicking elsewhere.
  var langs = document.querySelector(".langs");
  document.addEventListener("click", function (e) {
    if (langs && langs.open && !langs.contains(e.target)) langs.open = false;
  });
})();
