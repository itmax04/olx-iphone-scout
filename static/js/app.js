/* OLX iPhone Scout: CSRF for HTMX, copy buttons, password toggle. No inline JS. */

(function () {
  "use strict";

  function getCookie(name) {
    var value = "; " + document.cookie;
    var parts = value.split("; " + name + "=");
    if (parts.length === 2) {
      return parts.pop().split(";").shift();
    }
    return "";
  }

  document.addEventListener("htmx:configRequest", function (event) {
    event.detail.headers["X-CSRFToken"] = getCookie("csrftoken");
  });

  document.addEventListener("click", function (event) {
    var copyBtn = event.target.closest("[data-copy-target]");
    if (copyBtn) {
      var target = document.querySelector(copyBtn.getAttribute("data-copy-target"));
      if (target && navigator.clipboard) {
        navigator.clipboard.writeText(target.textContent.trim()).then(function () {
          var original = copyBtn.textContent;
          copyBtn.textContent = "Скопировано";
          setTimeout(function () {
            copyBtn.textContent = original;
          }, 1500);
        });
      }
      return;
    }

    var toggleBtn = event.target.closest("[data-password-toggle]");
    if (toggleBtn) {
      var input = document.querySelector(toggleBtn.getAttribute("data-password-toggle"));
      if (input) {
        var isPassword = input.getAttribute("type") === "password";
        input.setAttribute("type", isPassword ? "text" : "password");
        toggleBtn.setAttribute("aria-pressed", isPassword ? "true" : "false");
        toggleBtn.textContent = isPassword ? "Скрыть" : "Показать";
      }
    }
  });

  // Prevent accidental double submits: disable the button after first click.
  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (form.dataset.submitting === "1") {
      event.preventDefault();
      return;
    }
    form.dataset.submitting = "1";
    var buttons = form.querySelectorAll("button[type=submit]");
    setTimeout(function () {
      buttons.forEach(function (btn) {
        btn.disabled = true;
      });
    }, 0);
    setTimeout(function () {
      form.dataset.submitting = "";
      buttons.forEach(function (btn) {
        btn.disabled = false;
      });
    }, 5000);
  });
})();
