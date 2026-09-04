/* Browser client for the backend authentication API. */
(function (global) {
  "use strict";
  var API_BASE = "http://localhost:8000/api/auth";
  function request(path, options) {
    options = options || {};
    options.headers = Object.assign({ "Content-Type": "application/json" }, options.headers || {});
    options.credentials = "include";
    var url = /^https?:\/\//i.test(path) ? path : API_BASE + path;
    return fetch(url, options).catch(function () {
      throw new Error("Could not reach the backend at http://localhost:8000. Start the FastAPI server and try again.");
    }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok) {
          var detail = data.detail;
          if (Array.isArray(detail)) detail = detail.map(function (item) { return (item.loc ? item.loc.join('.') + ': ' : '') + item.msg; }).join(' ');
          throw new Error(detail || data.message || "Request failed");
        }
        return data;
      });
    });
  }
  global.LLAuth = {
    signup: function (data) { return request("/signup", { method: "POST", body: JSON.stringify(data) }); },
    verifyEmail: function (data) { return request("/verify-email", { method: "POST", body: JSON.stringify(data) }); },
    resendVerification: function (email) { return request("/resend-verification", { method: "POST", body: JSON.stringify({ email: email }) }); },
    login: function (data) { return request("/login", { method: "POST", body: JSON.stringify(data) }); },
    logout: function () { return request("/logout", { method: "POST" }); },
    me: function () { return request("/me"); },
    forgotPassword: function (email) { return request("/forgot-password", { method: "POST", body: JSON.stringify({ email: email }) }); },
    resetPassword: function (data) { return request("/reset-password", { method: "POST", body: JSON.stringify(data) }); },
    profile: function () { return request("/profile"); },
    updateProfile: function (data) { return request("/profile", { method: "PUT", body: JSON.stringify(data) }); },
    history: function () { return request("/history"); },
    dashboard: function () { return request("/dashboard"); }
  };
  global.LLManufacturer = {
    products: function () { return request("http://localhost:8000/api/manufacturer/products"); },
    createProduct: function (data) { return request("http://localhost:8000/api/manufacturer/products", { method: "POST", body: JSON.stringify(data) }); },
    revisions: function () { return request("http://localhost:8000/api/manufacturer/revisions"); },
    selfCheck: function (file, productId, productName) {
      var formData = new FormData();
      formData.append("file", file, file.name);
      formData.append("product_id", productId || "");
      formData.append("product_name", productName || "");
      return fetch("http://localhost:8000/api/manufacturer/self-check", { method: "POST", body: formData, credentials: "include" }).then(function (response) {
        return response.json().then(function (data) {
          if (!response.ok) throw new Error(data.detail || "Self-check failed");
          return data;
        });
      });
    }
  };
  if (["profile.html"].indexOf((global.location.pathname.split("/").pop() || "").toLowerCase()) !== -1) {
    var profileHeader = document.createElement("script");
    profileHeader.src = "assets/manufacturer-header.js";
    document.head.appendChild(profileHeader);
  }
  if ((global.location.pathname.split("/").pop() || "").toLowerCase() === "verify-email.html") {
    var verifyStyle = document.createElement("style");
    verifyStyle.textContent = "body{background:#f8f9fa!important}.verify-card{border-radius:12px;box-shadow:0 12px 32px rgba(0,39,74,.08)}.verify-title{letter-spacing:-.02em}.verify-intro{line-height:1.6}.otp-field{position:absolute!important;width:1px!important;height:1px!important;opacity:0!important;pointer-events:none!important}.otp-boxes{display:flex;gap:10px;width:100%;margin-top:10px}.otp-box{width:100%;height:58px;text-align:center;font-size:24px;font-weight:700;color:#00274a;background:#f8fafc;border:2px solid #cbd5e1;border-radius:8px;outline:none;transition:border-color .2s ease,box-shadow .2s ease,background-color .2s ease}.otp-box:focus{background:#fff;border-color:#006a6a;box-shadow:0 0 0 4px rgba(0,106,106,.12)}.verify-submit{min-height:48px;transition:background-color .2s ease,transform .2s ease}.verify-submit:hover{transform:translateY(-1px)}.verify-label{font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#475569}@media(max-width:480px){main.verify-card{padding:24px}.otp-boxes{gap:6px}.otp-box{height:54px;font-size:22px}}";
    document.head.appendChild(verifyStyle);
    document.addEventListener("DOMContentLoaded", function () {
      var card = document.querySelector("body > main");
      var otp = document.getElementById("otp");
      var form = document.getElementById("form");
      if (card) card.classList.add("verify-card");
      if (otp) {
        otp.classList.add("otp-field");
        var boxes = document.createElement("div");
        boxes.className = "otp-boxes";
        boxes.setAttribute("aria-label", "Enter six-digit verification code");
        for (var index = 0; index < 6; index += 1) {
          var box = document.createElement("input");
          box.className = "otp-box";
          box.type = "text";
          box.inputMode = "numeric";
          box.maxLength = 1;
          box.pattern = "[0-9]";
          box.setAttribute("aria-label", "Verification digit " + (index + 1));
          boxes.appendChild(box);
        }
        otp.parentNode.insertBefore(boxes, otp.nextSibling);
        var digitInputs = boxes.querySelectorAll(".otp-box");
        function syncOtp() {
          var value = Array.prototype.map.call(digitInputs, function (input) { return input.value; }).join("");
          otp.value = value;
        }
        digitInputs.forEach(function (input, index) {
          input.addEventListener("input", function () {
            input.value = input.value.replace(/[^0-9]/g, "").slice(-1);
            syncOtp();
            if (input.value && digitInputs[index + 1]) digitInputs[index + 1].focus();
          });
          input.addEventListener("keydown", function (event) {
            if (event.key === "Backspace" && !input.value && digitInputs[index - 1]) digitInputs[index - 1].focus();
          });
          input.addEventListener("paste", function (event) {
            var pasted = (event.clipboardData || global.clipboardData).getData("text").replace(/[^0-9]/g, "").slice(0, 6);
            if (!pasted) return;
            event.preventDefault();
            Array.prototype.forEach.call(digitInputs, function (digit, digitIndex) { digit.value = pasted[digitIndex] || ""; });
            syncOtp();
            digitInputs[Math.min(pasted.length, 6) - 1].focus();
          });
        });
        digitInputs[0].addEventListener("focus", function () { boxes.classList.add("is-focused"); });
        digitInputs[5].addEventListener("blur", function () { boxes.classList.remove("is-focused"); });
      }
      if (form && otp) {
        var label = document.createElement("label");
        label.className = "verify-label";
        label.htmlFor = "otp";
        label.textContent = "Verification code";
        otp.parentNode.insertBefore(label, otp);
      }
    });
  }
})(window);
