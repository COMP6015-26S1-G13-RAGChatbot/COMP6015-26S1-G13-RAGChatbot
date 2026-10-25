(function () {
  "use strict";

  var $ = function (id) { return document.getElementById(id); };
  var form = $("authForm");
  var username = $("username");
  var password = $("password");
  var confirm = $("confirm");
  var submit = $("submit");
  var error = $("error");
  var mode = "signin";

  function showError(message) {
    error.textContent = message;
    error.hidden = !message;
  }

  function setMode(next) {
    mode = next;
    var signup = mode === "signup";
    $("tabSignin").setAttribute("aria-selected", String(!signup));
    $("tabSignup").setAttribute("aria-selected", String(signup));
    $("formTitle").textContent = signup ? "Create an account" : "Sign in";
    submit.textContent = signup ? "Create account" : "Sign in";
    $("confirmRow").hidden = !signup;
    $("hint").hidden = !signup;
    confirm.required = signup;
    password.setAttribute("autocomplete", signup ? "new-password" : "current-password");
    showError("");
    username.focus();
  }

  $("tabSignin").addEventListener("click", function () { setMode("signin"); });
  $("tabSignup").addEventListener("click", function () { setMode("signup"); });

  // Hide "Create account" when the server has sign-up switched off.
  fetch("/api/auth/config")
    .then(function (r) { return r.json(); })
    .then(function (cfg) {
      if (!cfg.signup) {
        $("tabs").hidden = true;
        $("closedNote").hidden = false;
      }
    })
    .catch(function () {});

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var name = username.value.trim();

    if (!name || !password.value) {
      return showError("Enter your username and password.");
    }
    if (mode === "signup") {
      if (!/^[A-Za-z0-9._-]{3,32}$/.test(name)) {
        return showError("Usernames must be 3–32 characters: letters, numbers, dots, hyphens or underscores.");
      }
      if (password.value.length < 8) {
        return showError("Passwords must be at least 8 characters.");
      }
      if (password.value !== confirm.value) {
        return showError("The two passwords don't match.");
      }
    }

    submit.disabled = true;
    showError("");

    fetch(mode === "signup" ? "/api/signup" : "/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: name, password: password.value })
    })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (data) {
          if (!res.ok) {
            var detail = data.detail;
            throw new Error(typeof detail === "string" ? detail : "Something went wrong (" + res.status + ").");
          }
          window.location.replace("/");
        });
      })
      .catch(function (err) {
        showError(err.message === "Failed to fetch" ? "Could not reach the server." : err.message);
        password.value = "";
        confirm.value = "";
        password.focus();
        submit.disabled = false;
      });
  });
})();
