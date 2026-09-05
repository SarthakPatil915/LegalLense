/* Shared Official header. User identity comes from /api/auth/me, never from page markup. */
(function (global) {
  "use strict";

  var pages = {
    "official-dashboard.html": "Dashboard",
    "new-compliance-scan.html": "New Scan",
    "case-details.html": "Cases",
    "log-case-action.html": "Cases",
    "compliance-report.html": "Reports",
    "scan-history.html": "History"
  };

  function escape(value) {
    return global.LL && global.LL.escapeHtml ? global.LL.escapeHtml(value) : String(value || "");
  }

  function currentPage() {
    return (global.location.pathname.split("/").pop() || "official-dashboard.html").toLowerCase();
  }

  function render(user) {
    var sidebar = document.querySelector(".official-sidebar, body > aside.fixed, body > nav.fixed");
    var shell = Array.prototype.find.call(document.body.children, function (child) {
      return child !== sidebar && (child.tagName.toLowerCase() === "main" || child.querySelector("main") || child.querySelector("header"));
    });
    document.querySelectorAll("header").forEach(function (header) {
      header.remove();
    });
    var header = document.createElement("header");
    document.body.classList.add("official-layout");
    if (shell) shell.classList.add("official-page-shell");
    if (sidebar) {
      sidebar.classList.add("official-page-sidebar");
      var page = currentPage();
      sidebar.querySelectorAll("a[href]").forEach(function (link) {
        var path = (link.getAttribute("href") || "").split("#")[0].split("?")[0].split("/").pop().toLowerCase();
        link.classList.remove("border-secondary-fixed-dim", "bg-on-primary-fixed-variant/10", "text-secondary-fixed-dim", "font-bold", "opacity-90");
        link.classList.toggle("official-active", path === page);
      });
    }
    header.className = "ll-official-header";
    header.innerHTML =
      '<a class="ll-official-brand" href="official-dashboard.html" aria-label="LegalLens Official Dashboard">' +
        '<img src="assets/page-previews/Logo.png" alt="LegalLens" style="display:block;width:auto;height:40px;max-width:180px;object-fit:contain" />' +
      '</a>' +
      '<nav class="ll-official-nav" aria-label="Official navigation">' +
        '<a href="official-dashboard.html">Dashboard</a>' +
        '<a href="new-compliance-scan.html">New Scan</a>' +
        '<a href="scan-history.html">History</a>' +
        '<a href="case-details.html">Cases</a>' +
        '<a href="compliance-report.html">Reports</a>' +
      '</nav>' +
      '<div class="ll-official-actions">' +
        '<span class="ll-official-role">OFFICIAL</span>' +
        '<button class="ll-profile-button" type="button" aria-label="Open official profile" aria-expanded="false">' +
          '<span class="material-symbols-outlined">person</span>' +
        '</button>' +
        '<div class="ll-profile-menu" hidden>' +
          '<div class="ll-profile-heading"><span class="material-symbols-outlined">account_circle</span><div><strong class="ll-profile-name">' + escape(user.fullName) + '</strong><span class="ll-profile-email">' + escape(user.email) + '</span></div></div>' +
          '<div class="ll-profile-meta"><div>Account: <strong>Official</strong></div><div class="ll-verified"><span class="material-symbols-outlined">' + (user.emailVerified ? "verified" : "warning") + '</span> ' + (user.emailVerified ? "Email Verified" : "Email Not Verified") + '</div></div>' +
          '<a href="profile.html">Profile</a><a href="official-dashboard.html">Dashboard</a><a href="scan-history.html">History</a><a href="settings.html">Settings</a>' +
          '<button class="ll-profile-logout" type="button"><span class="material-symbols-outlined">logout</span>Logout</button>' +
        '</div>' +
      '</div>';

    document.body.insertBefore(header, document.body.firstChild);
    var active = pages[currentPage()] || "Dashboard";
    header.querySelectorAll(".ll-official-nav a").forEach(function (link) {
      link.classList.toggle("is-active", link.textContent.trim() === active);
    });

    var button = header.querySelector(".ll-profile-button");
    var menu = header.querySelector(".ll-profile-menu");
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
    header.querySelector(".ll-profile-logout").addEventListener("click", function () {
      global.LLAuth.logout().catch(function () {}).finally(function () {
        sessionStorage.removeItem("legallense_session_v1");
        global.location.replace("login.html?role=official");
      });
    });
  }

  function start() {
    if (!global.LLAuth || !global.LLAuth.me) return;
    global.LLAuth.me().then(function (result) {
      if (!result.user || result.user.role !== "official") throw new Error("official role required");
      render(result.user);
    }).catch(function () {
      sessionStorage.removeItem("legallense_session_v1");
      global.location.replace("login.html?role=official");
    });
  }

  var style = document.createElement("style");
  style.textContent = ".ll-official-header{height:64px;display:flex;align-items:center;gap:24px;padding:0 32px;background:#f8f9fa;border-bottom:1px solid #c3c6d0;position:sticky;top:0;z-index:60;font-family:Inter,sans-serif}.ll-official-brand{display:flex;align-items:center;gap:8px;color:#00274a;font-weight:700;text-decoration:none;white-space:nowrap}.ll-official-brand .material-symbols-outlined{font-size:24px}.ll-official-nav{display:flex;align-items:center;gap:20px;flex:1}.ll-official-nav a{color:#42474f;text-decoration:none;font-size:14px;font-weight:600;padding:21px 0 18px;border-bottom:2px solid transparent;white-space:nowrap}.ll-official-nav a:hover,.ll-official-nav a.is-active{color:#00274a;border-bottom-color:#00274a}.ll-official-actions{display:flex;align-items:center;gap:12px;position:relative}.ll-official-role{color:#006a6a;font-size:12px;font-weight:800;letter-spacing:.08em}.ll-profile-button{width:38px;height:38px;border:1px solid #c3c6d0;border-radius:50%;background:#fff;color:#00274a;display:flex;align-items:center;justify-content:center;cursor:pointer}.ll-profile-menu{position:absolute;right:0;top:48px;width:280px;background:#fff;border:1px solid #c3c6d0;border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,.14);padding:8px;color:#191c1d}.ll-profile-menu a,.ll-profile-logout{display:flex;align-items:center;gap:10px;width:100%;box-sizing:border-box;padding:10px 12px;color:#42474f;text-decoration:none;background:none;border:0;font:600 14px Inter,sans-serif;text-align:left;cursor:pointer}.ll-profile-menu a:hover,.ll-profile-logout:hover{background:#f3f4f5;color:#00274a}.ll-profile-heading{display:flex;gap:10px;padding:12px;border-bottom:1px solid #e1e3e4}.ll-profile-heading>.material-symbols-outlined{color:#006a6a;font-size:28px}.ll-profile-name,.ll-profile-email{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.ll-profile-email{font-size:12px;color:#737780;margin-top:3px}.ll-profile-meta{padding:12px;border-bottom:1px solid #e1e3e4;font-size:12px;color:#42474f;line-height:20px}.ll-verified{color:#006a6a}.ll-verified .material-symbols-outlined{font-size:15px;vertical-align:middle}@media(max-width:800px){.ll-official-header{padding:0 16px;gap:14px}.ll-official-nav{gap:12px;overflow-x:auto}.ll-official-nav a{font-size:12px;padding:22px 0 19px}.ll-official-role{display:none}}@media(max-width:560px){.ll-official-brand span:last-child{display:none}.ll-official-nav{gap:10px}.ll-official-nav a{font-size:11px}.ll-profile-menu{right:-8px;width:min(280px,calc(100vw - 24px))}}";
  document.head.appendChild(style);
  var flexStyle = document.createElement("style");
  flexStyle.id = "official-header-flex-style";
  flexStyle.textContent = ".ll-official-header{display:flex!important;align-items:center!important;justify-content:space-between!important;box-sizing:border-box!important;width:auto!important;min-width:0!important;overflow:visible!important}.ll-official-brand{flex:0 0 auto!important}.ll-official-nav{display:flex!important;align-items:center!important;flex:1 1 auto!important;min-width:0!important;overflow-x:auto!important;overflow-y:hidden!important;white-space:nowrap!important;scrollbar-width:none!important}.ll-official-nav::-webkit-scrollbar{display:none}.ll-official-actions{flex:0 0 auto!important;margin-left:auto!important;white-space:nowrap!important;position:relative!important;z-index:1000!important}.ll-official-role{white-space:nowrap!important}.ll-profile-menu{z-index:9999!important}@media(max-width:767px){.ll-official-header{padding-left:16px!important;padding-right:16px!important;gap:12px!important}.ll-official-nav{gap:12px!important}.ll-official-actions{gap:8px!important}}";
  document.head.appendChild(flexStyle);
  var layoutStyle = document.createElement("style");
  layoutStyle.id = "official-layout-style";
  layoutStyle.textContent = ".official-layout{box-sizing:border-box;overflow-x:hidden}.official-layout *,.official-layout *::before,.official-layout *::after{box-sizing:border-box}.official-layout .official-page-sidebar{width:260px!important;min-width:260px!important;padding-top:24px!important;padding-bottom:24px!important;background:#00274a!important;z-index:70}.official-layout .official-page-sidebar a{min-height:48px!important;border-left:4px solid transparent!important;border-radius:0 4px 4px 0!important;padding:12px 16px!important;color:rgba(255,255,255,.72)!important;font-size:14px!important;line-height:20px!important}.official-layout .official-page-sidebar a:hover{color:#fff!important;background:rgba(255,255,255,.06)!important}.official-layout .official-page-sidebar a.official-active{border-left-color:#76d6d5!important;background:rgba(28,72,119,.45)!important;color:#76d6d5!important;font-weight:700!important}.official-layout .official-page-shell{margin-left:260px!important;min-width:0!important;width:calc(100% - 260px)!important;padding-top:64px!important}.official-layout .ll-official-header{position:fixed;top:0;right:0;left:260px;width:auto;z-index:80;min-width:0}.official-layout .ll-official-nav{min-width:0;overflow-x:auto;scrollbar-width:none}.official-layout .ll-official-nav::-webkit-scrollbar{display:none}@media(max-width:767px){.official-layout .official-page-sidebar{display:none!important}.official-layout .official-page-shell{margin-left:0!important;width:100%!important;padding-top:64px!important}.official-layout .ll-official-header{left:0}}";
  document.head.appendChild(layoutStyle);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})(window);
