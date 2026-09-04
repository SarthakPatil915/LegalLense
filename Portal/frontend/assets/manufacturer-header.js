/* Shared Manufacturer header. Identity is loaded from /api/auth/me. */
(function (global) {
  "use strict";

  var pages = {
    "manufacturer-dashboard.html": "Dashboard",
    "products.html": "Products",
    "new-self-check.html": "New Self Check",
    "self-check-report.html": "Reports",
    "compliance-summary.html": "Reports",
    "revision-history.html": "History",
    "settings.html": "Settings",
    "profile.html": "Profile"
  };

  function escape(value) {
    return global.LL && global.LL.escapeHtml ? global.LL.escapeHtml(value) : String(value || "");
  }

  function currentPage() {
    return (global.location.pathname.split("/").pop() || "manufacturer-dashboard.html").toLowerCase();
  }

  function render(user) {
    var sidebar = document.querySelector(".manufacturer-sidebar, body > aside.fixed, body > nav.fixed");
    var shell = Array.prototype.find.call(document.body.children, function (child) {
      return child !== sidebar && (child.tagName.toLowerCase() === "main" || child.querySelector("main") || child.querySelector("header"));
    });
    var existing = document.querySelector("header");
    document.querySelectorAll("header").forEach(function (header) {
      if (header !== existing) header.remove();
    });
    var header = existing || document.createElement("header");
    document.body.classList.add("manufacturer-layout");
    if (pages[currentPage()] === "Reports") document.body.classList.add("manufacturer-reports-page");
    document.querySelectorAll("a").forEach(function (link) {
      if (link.textContent.replace(/\s+/g, " ").trim().toLowerCase() === "support") {
        var item = link.parentElement && link.parentElement.tagName.toLowerCase() === "li" ? link.parentElement : link;
        item.remove();
      }
    });
    if (shell) shell.classList.add("manufacturer-page-shell");
    if (sidebar) sidebar.classList.add("manufacturer-page-sidebar");
    if (!sidebar && shell) {
      shell.classList.add("manufacturer-no-sidebar");
      document.body.classList.add("manufacturer-no-sidebar-layout");
    }
    header.className = "ll-manufacturer-header";
    header.innerHTML =
      '<a class="ll-manufacturer-brand" href="manufacturer-dashboard.html" aria-label="LegalLense Manufacturer Dashboard">' +
        '<span class="material-symbols-outlined">policy</span><span>LegalLense</span>' +
      '</a>' +
      '<nav class="ll-manufacturer-nav" aria-label="Manufacturer navigation">' +
        '<a href="manufacturer-dashboard.html">Dashboard</a>' +
        '<a href="products.html">Products</a>' +
        '<a href="new-self-check.html">New Self Check</a>' +
        '<a href="self-check-report.html">Reports</a>' +
        '<a href="revision-history.html">History</a>' +
      '</nav>' +
      '<div class="ll-manufacturer-actions">' +
        '<span class="ll-manufacturer-role">MANUFACTURER</span>' +
        '<button class="ll-manufacturer-profile-button" type="button" aria-label="Open manufacturer profile" aria-expanded="false"><span class="material-symbols-outlined">person</span></button>' +
        '<div class="ll-manufacturer-profile-menu" hidden>' +
          '<div class="ll-manufacturer-profile-heading"><span class="material-symbols-outlined">account_circle</span><div><strong>' + escape(user.fullName) + '</strong><span>' + escape(user.email) + '</span></div></div>' +
          '<div class="ll-manufacturer-profile-meta"><div>Company: <strong>' + escape(user.companyName || "Not provided") + '</strong></div><div>Account: <strong>Manufacturer</strong></div><div class="ll-manufacturer-verified"><span class="material-symbols-outlined">' + (user.emailVerified ? "verified" : "warning") + '</span> ' + (user.emailVerified ? "Email Verified" : "Email Not Verified") + '</div></div>' +
          '<a href="profile.html">Profile</a><a href="manufacturer-dashboard.html">Dashboard</a><a href="products.html">Products</a><a href="revision-history.html">History</a><a href="settings.html">Settings</a>' +
          '<button class="ll-manufacturer-logout" type="button"><span class="material-symbols-outlined">logout</span>Logout</button>' +
        '</div>' +
      '</div>';

    if (sidebar) {
      var sidebarPage = currentPage();
      if (pages[sidebarPage] === "Reports") sidebarPage = "new-self-check.html";
      sidebar.querySelectorAll("a[href]").forEach(function (link) {
        var path = (link.getAttribute("href") || "").split("#")[0].split("?")[0].split("/").pop().toLowerCase();
        link.classList.remove("border-secondary-fixed-dim", "bg-on-primary-fixed-variant/10", "text-secondary-fixed-dim", "font-bold", "opacity-90");
        link.classList.toggle("manufacturer-active", path === sidebarPage);
      });
    }

    if (!existing) document.body.insertBefore(header, document.body.firstChild);
    else if (header.parentElement !== document.body) document.body.insertBefore(header, document.body.firstChild);
    var active = pages[currentPage()] || "Dashboard";
    header.querySelectorAll(".ll-manufacturer-nav a").forEach(function (link) {
      link.classList.toggle("is-active", link.textContent.trim() === active);
    });

    var button = header.querySelector(".ll-manufacturer-profile-button");
    var menu = header.querySelector(".ll-manufacturer-profile-menu");
    function closeMenu() {
      menu.hidden = true;
      button.setAttribute("aria-expanded", "false");
    }
    button.addEventListener("click", function (event) {
      event.stopPropagation();
      menu.hidden = !menu.hidden;
      button.setAttribute("aria-expanded", String(!menu.hidden));
    });
    document.addEventListener("click", function (event) {
      if (!header.contains(event.target)) closeMenu();
    });
    header.querySelector(".ll-manufacturer-logout").addEventListener("click", function () {
      global.LLAuth.logout().catch(function () {}).finally(function () {
        sessionStorage.removeItem("legallense_session_v1");
        global.location.replace("login.html?role=manufacturer");
      });
    });
  }

  function start() {
    if (global.__manufacturerHeaderStarted) return;
    global.__manufacturerHeaderStarted = true;
    if (!global.LLAuth || !global.LLAuth.me) return;
    global.LLAuth.me().then(function (result) {
      if (!result.user || result.user.role !== "manufacturer") throw new Error("manufacturer role required");
      render(result.user);
    }).catch(function () {
      sessionStorage.removeItem("legallense_session_v1");
      global.location.replace("login.html?role=manufacturer");
    });
  }

  var style = document.createElement("style");
  style.textContent = ".ll-manufacturer-header{height:64px;display:flex;align-items:center;gap:24px;padding:0 32px;background:#f8f9fa;border-bottom:1px solid #c3c6d0;position:sticky;top:0;z-index:60;font-family:Inter,sans-serif}.ll-manufacturer-brand{display:flex;align-items:center;gap:8px;color:#00274a;font-weight:700;text-decoration:none;white-space:nowrap}.ll-manufacturer-brand .material-symbols-outlined{font-size:24px}.ll-manufacturer-nav{display:flex;align-items:center;gap:20px;flex:1}.ll-manufacturer-nav a{color:#42474f;text-decoration:none;font-size:14px;font-weight:600;padding:21px 0 18px;border-bottom:2px solid transparent;white-space:nowrap}.ll-manufacturer-nav a:hover,.ll-manufacturer-nav a.is-active{color:#00274a;border-bottom-color:#00274a}.ll-manufacturer-actions{display:flex;align-items:center;gap:12px;position:relative}.ll-manufacturer-role{color:#006a6a;font-size:12px;font-weight:800;letter-spacing:.08em}.ll-manufacturer-profile-button{width:38px;height:38px;border:1px solid #c3c6d0;border-radius:50%;background:#fff;color:#00274a;display:flex;align-items:center;justify-content:center;cursor:pointer}.ll-manufacturer-profile-menu{position:absolute;right:0;top:48px;width:300px;background:#fff;border:1px solid #c3c6d0;border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,.14);padding:8px;color:#191c1d}.ll-manufacturer-profile-menu a,.ll-manufacturer-logout{display:flex;align-items:center;gap:10px;width:100%;box-sizing:border-box;padding:10px 12px;color:#42474f;text-decoration:none;background:none;border:0;font:600 14px Inter,sans-serif;text-align:left;cursor:pointer}.ll-manufacturer-profile-menu a:hover,.ll-manufacturer-logout:hover{background:#f3f4f5;color:#00274a}.ll-manufacturer-profile-heading{display:flex;gap:10px;padding:12px;border-bottom:1px solid #e1e3e4}.ll-manufacturer-profile-heading>.material-symbols-outlined{color:#006a6a;font-size:28px}.ll-manufacturer-profile-heading strong,.ll-manufacturer-profile-heading span{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.ll-manufacturer-profile-heading span{font-size:12px;color:#737780;margin-top:3px}.ll-manufacturer-profile-meta{padding:12px;border-bottom:1px solid #e1e3e4;font-size:12px;color:#42474f;line-height:20px}.ll-manufacturer-verified{color:#006a6a}.ll-manufacturer-verified .material-symbols-outlined{font-size:15px;vertical-align:middle}@media(max-width:800px){.ll-manufacturer-header{padding:0 16px;gap:14px}.ll-manufacturer-nav{gap:12px;overflow-x:auto}.ll-manufacturer-nav a{font-size:12px;padding:22px 0 19px}.ll-manufacturer-role{display:none}}@media(max-width:560px){.ll-manufacturer-brand span:last-child{display:none}.ll-manufacturer-nav{gap:10px}.ll-manufacturer-nav a{font-size:11px}.ll-manufacturer-profile-menu{right:-8px;width:min(300px,calc(100vw - 24px))}}";
  document.head.appendChild(style);
  var layoutStyle = document.createElement("style");
  layoutStyle.id = "manufacturer-layout-style";
  layoutStyle.textContent = ".manufacturer-layout{box-sizing:border-box;overflow-x:hidden}.manufacturer-layout *,.manufacturer-layout *::before,.manufacturer-layout *::after{box-sizing:border-box}.manufacturer-layout .manufacturer-page-sidebar{width:300px!important;min-width:300px!important;z-index:70;padding-top:24px!important;padding-bottom:24px!important;background:#00274a!important}.manufacturer-layout .manufacturer-page-sidebar a{min-height:48px!important;border-left:4px solid transparent!important;border-radius:0 8px 8px 0!important;padding:12px 16px!important;color:rgba(255,255,255,.72)!important;font-size:14px!important;line-height:20px!important}.manufacturer-layout .manufacturer-page-sidebar a:hover{color:#fff!important;background:rgba(255,255,255,.06)!important}.manufacturer-layout .manufacturer-page-sidebar a.manufacturer-active{border-left-color:#76d6d5!important;background:rgba(28,72,119,.45)!important;color:#76d6d5!important;font-weight:700!important}.manufacturer-layout .manufacturer-page-shell{margin-left:300px!important;min-width:0!important;width:calc(100% - 300px)!important;padding-top:64px!important}.manufacturer-layout .manufacturer-page-shell.manufacturer-no-sidebar{margin-left:0!important;width:100%!important}.manufacturer-layout .ll-manufacturer-header{position:fixed;top:0;right:0;left:300px;width:auto;z-index:80;min-width:0}.manufacturer-layout.manufacturer-no-sidebar-layout .ll-manufacturer-header{left:0}.manufacturer-layout .manufacturer-page-shell>main,.manufacturer-layout .manufacturer-page-shell>div{min-width:0}.manufacturer-layout .manufacturer-reports-page .manufacturer-page-shell>div,.manufacturer-layout .manufacturer-reports-page .manufacturer-page-shell>main>div{max-width:1440px!important;width:100%!important;margin-left:auto!important;margin-right:auto!important;padding-left:32px!important;padding-right:32px!important}.manufacturer-layout .manufacturer-reports-page .manufacturer-page-shell>div>nav,.manufacturer-layout .manufacturer-reports-page .manufacturer-page-shell>main>div>nav{margin-bottom:24px!important}.manufacturer-layout .ll-manufacturer-nav{min-width:0;overflow-x:auto;scrollbar-width:none}.manufacturer-layout .ll-manufacturer-nav::-webkit-scrollbar{display:none}@media(max-width:767px){.manufacturer-layout .manufacturer-page-sidebar{display:none!important}.manufacturer-layout .manufacturer-page-shell{margin-left:0!important;width:100%!important;padding-top:64px!important}.manufacturer-layout .ll-manufacturer-header{left:0}.manufacturer-layout .manufacturer-reports-page .manufacturer-page-shell>div,.manufacturer-layout .manufacturer-reports-page .manufacturer-page-shell>main>div{padding-left:16px!important;padding-right:16px!important}}";
  document.head.appendChild(layoutStyle);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})(window);
