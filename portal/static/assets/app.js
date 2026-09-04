/* ============ 云锡统一门户 — 前端单页逻辑(Vanilla JS, 无框架依赖) ============ */
(function () {
  "use strict";

  var app = document.getElementById("app");
  var API = location.pathname.replace(/[^/]*$/, "") + "api/v1";
  var currentUser = null;

  // SSO 回跳：平台未登录跳转过来时携带 ?redirect=<平台地址>
  var REDIRECT = (function () {
    try {
      var p = new URLSearchParams(location.search).get("redirect");
      if (p && (function(u){ try { return new URL(u).host === location.host; } catch(e) { return false; } })(p)) return p;
    } catch (e) {}
    return null;
  })();

  // 云图标(对齐两个现有平台左上角的品牌图标)
  var CLOUD_ICON = '<svg viewBox="0 0 24 24" fill="currentColor">' +
    '<path d="M19.35 10.04C18.67 6.59 15.64 4 12 4 9.11 4 6.6 5.64 5.35 8.04 2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96z"/></svg>';

  // 密码可见性切换的眼睛图标（开眼 / 闭眼）
  var EYE_OPEN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8S1 12 1 12z"/><circle cx="12" cy="12" r="3"/></svg>';
  var EYE_CLOSED = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.94 10.94 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 4.06-5.94M9.9 4.24A10.94 10.94 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';

  // 平台导航图标(从两个平台前端真实复用, 与实际菜单一致)
  var ICON_CHART = '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zM9 17H7v-7h2v7zm4 0h-2V7h2v10zm4 0h-2v-4h2v4z"/></svg>';
  var ICON_BRAIN = '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M9 21c0 .5.4 1 1 1h4c.6 0 1-.5 1-1v-1H9v1zm3-19C8.1 2 5 5.1 5 9c0 2.4 1.2 4.5 3 5.7V17c0 .5.4 1 1 1h6c.6 0 1-.5 1-1v-2.3c1.8-1.3 3-3.4 3-5.7c0-3.9-3.1-7-7-7z"/></svg>';
  var ICON_CLOCK = '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M13 3c-4.97 0-9 4.03-9 9H1l3.89 3.89l.07.14L9 12H6c0-3.87 3.13-7 7-7s7 3.13 7 7s-3.13 7-7 7c-1.93 0-3.68-.79-4.94-2.06l-1.42 1.42C8.27 19.99 10.51 21 13 21c4.97 0 9-4.03 9-9s-4.03-9-9-9zm-1 5v5l4.28 2.54l.72-1.21l-3.5-2.08V8H12z"/></svg>';
  var ICON_UPLOAD = '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M19.35 10.04C18.67 6.59 15.64 4 12 4 9.11 4 6.6 5.64 5.35 8.04 2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM14 13v4h-4v-4H7l5-5 5 5h-3z"/></svg>';
  var ICON_DOC = '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 14H7v-2h5v2zm5-4H7v-2h10v2zm0-4H7V7h10v2z"/></svg>';
  var ICON_GLOBE = '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg>';

  // 各平台真实导航项(与前端 menuOptions 一致)
  var PLATFORM_NAV = {
    compute: [
      { name: "数据平台", icon: ICON_CHART },
      { name: "智能推理", icon: ICON_BRAIN },
      { name: "操作记录", icon: ICON_CLOCK }
    ],
    data: [
      { name: "系统总览", icon: ICON_CHART },
      { name: "上传文件", icon: ICON_UPLOAD },
      { name: "处理日志", icon: ICON_DOC },
      { name: "数据来源", icon: ICON_GLOBE }
    ]
  };

  function eyeToggleSvg() {
    return '<button type="button" class="toggle-eye" aria-label="切换密码可见性" title="显示/隐藏密码">' + EYE_CLOSED + '</button>';
  }

  // 监听全局点击，切换同 field 内的 password <-> text
  document.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest(".toggle-eye");
    if (!btn) return;
    var field = btn.closest(".password-field");
    if (!field) return;
    var input = field.querySelector("input[name='password']");
    if (!input) return;
    if (input.type === "password") {
      input.type = "text";
      btn.innerHTML = EYE_OPEN;
      btn.setAttribute("aria-pressed", "true");
    } else {
      input.type = "password";
      btn.innerHTML = EYE_CLOSED;
      btn.setAttribute("aria-pressed", "false");
    }
  });

  function api(path, opts) {
    opts = opts || {};
    opts.credentials = "include";
    opts.headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
    return fetch(API + path, opts).then(function (r) {
      return r.text().then(function (txt) {
        var data = txt ? JSON.parse(txt) : null;
        if (!r.ok) {
          var msg = (data && data.detail) || ("请求失败 (" + r.status + ")");
          throw new Error(msg);
        }
        return data;
      });
    });
  }

  function el(html) {
    var t = document.createElement("template");
    t.innerHTML = html.trim();
    return t.content.firstChild;
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function route() {
    var h = location.hash.replace(/^#/, "") || "/login";
    if (h === "/login" || h === "/register") return renderAuth(h === "/register");
    if (!currentUser) {
      return api("/auth/me").then(function (u) {
        currentUser = u;
        renderProtected(h);
      }).catch(function () {
        location.hash = "/login";
      });
    }
    renderProtected(h);
  }

  function renderProtected(h) {
    if (h === "/admin" && currentUser.role === "Admin") return renderAdmin();
    if (h === "/admin") { location.hash = "/home"; return; }
    renderHome();
  }

  /* ---------- 登录 / 注册 ---------- */
  function renderAuth(isRegister) {
    var registerFields =
      '<div class="field"><label>用户名<span class="req">*</span></label><input name="username" placeholder="3-32 个字符" autocomplete="username" /></div>' +
      '<div class="field"><label>邮箱<span class="req">*</span></label><input name="email" type="email" placeholder="example@mail.com" /></div>' +
      '<div class="field"><label>显示名称（选填）</label><input name="display" placeholder="如 张工" /></div>' +
      '<div class="field password-field"><label>密码<span class="req">*</span></label><div class="input-box"><input name="password" type="password" placeholder="至少 6 位" autocomplete="new-password" />' + eyeToggleSvg() + '</div></div>' +
      '<div class="field password-field"><label>确认密码<span class="req">*</span></label><div class="input-box"><input name="password2" type="password" placeholder="再次输入密码" autocomplete="new-password" />' + eyeToggleSvg() + '</div></div>';

    var card = el(
      '<div class="auth-page"><div class="auth-card">' +
        '<div class="brand-logo"><span class="dot">' + CLOUD_ICON + '</span>' +
          '<span class="name">云锡统一门户</span></div>' +
        '<h1>' + (isRegister ? "创建账号" : "欢迎登录") + "</h1>" +
        '<div class="msg"></div>' +
        '<form>' +
          (isRegister
            ? registerFields
            : '<div class="field"><label>用户名</label><input name="username" placeholder="请输入用户名" autocomplete="username" /></div>' +
              '<div class="field password-field"><label>密码</label><div class="input-box"><input name="password" type="password" placeholder="请输入密码" autocomplete="current-password" />' + eyeToggleSvg() + '</div></div>') +
          '<button type="submit" class="btn-primary">' + (isRegister ? "注册" : "登 录") + "</button>" +
        "</form>" +
        '<div class="auth-switch">' +
          (isRegister
            ? '已有账号？ <a href="#/login">前往登录</a>'
            : '还没有账号？ <a href="#/register">立即注册</a>') +
        "</div>" +
      "</div></div>"
    );

    var msg = card.querySelector(".msg");
    var form = card.querySelector("form");
    var btn = card.querySelector(".btn-primary");

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      msg.innerHTML = "";
      var username = form.username.value.trim();
      var password = form.password.value;
      if (!username || !password) {
        msg.innerHTML = '<div class="auth-error">请填写用户名和密码</div>';
        return;
      }
      btn.disabled = true;
      var payload;
      if (isRegister) {
        var email = (form.email.value || "").trim();
        var password2 = form.password2.value;
        if (!email) {
          btn.disabled = false;
          msg.innerHTML = '<div class="auth-error">请填写邮箱</div>';
          return;
        }
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
          btn.disabled = false;
          msg.innerHTML = '<div class="auth-error">邮箱格式不正确</div>';
          return;
        }
        if (password.length < 6) {
          btn.disabled = false;
          msg.innerHTML = '<div class="auth-error">密码至少 6 位</div>';
          return;
        }
        if (password !== password2) {
          btn.disabled = false;
          msg.innerHTML = '<div class="auth-error">两次输入的密码不一致</div>';
          return;
        }
        payload = { username: username, password: password, email: email, display_name: form.display.value.trim() || username };
      } else {
        payload = { username: username, password: password };
      }
      var endpoint = isRegister ? "/auth/register" : "/auth/login";
      api(endpoint, { method: "POST", body: JSON.stringify(payload) })
        .then(function (res) {
          if (isRegister) {
            msg.innerHTML = '<div class="auth-ok">注册成功，正在跳转登录…</div>';
            setTimeout(function () { location.hash = "/login"; }, 800);
          } else {
            currentUser = res.user;
            if (REDIRECT) window.location.href = REDIRECT;
            else location.hash = "/home";
          }
        })
        .catch(function (err) {
          btn.disabled = false;
          msg.innerHTML = '<div class="auth-error">' + esc(err.message) + "</div>";
        });
    });

    app.innerHTML = "";
    app.appendChild(card);
  }

  /* ---------- 主页: 平台入口卡片 ---------- */
  function renderHome() {
    var displayName = currentUser.display_name || currentUser.username;
    var hour = new Date().getHours();
    var greet = hour < 6 ? "凌晨好" : hour < 12 ? "早上好" : hour < 14 ? "中午好" : hour < 18 ? "下午好" : "晚上好";

    var shell = el(
      '<div class="portal-shell">' +
        '<div class="topbar">' +
          '<div class="brand"><span class="dot">' + CLOUD_ICON + '</span>' +
            '<span class="name">云锡统一门户</span>' +
            '<span class="tag">Yunxi Platform</span></div>' +
          '<div class="user-menu"><span class="avatar"></span><span class="uname"></span>' +
            '<span class="caret">▼</span><div class="dropdown" style="display:none"></div></div>' +
        "</div>" +
        '<div class="page">' +
          '<div class="page-head">' +
            '<div class="greet">' + greet + '，<strong>' + esc(displayName) + '</strong></div>' +
            '<div class="greet-sub">请选择要进入的业务平台</div>' +
          '</div>' +
          '<div class="cards"></div>' +
          '<div class="demo-box">' +
            '<div class="demo-head"><span class="demo-ic">🔑</span>' +
              '<div><div class="demo-title">演示直登链接</div>' +
              '<div class="demo-sub">免输密码，打开即登录本账号（30 天有效），适合演示与分享</div></div></div>' +
            '<div class="demo-row">' +
              '<input class="demo-input" readonly placeholder="点击下方按钮生成…">' +
              '<button class="demo-copy">复制链接</button>' +
              '<button class="demo-gen">生成链接</button>' +
            '</div>' +
          '</div>' +
        "</div>" +
      "</div>"
    );

    shell.querySelector(".avatar").textContent = displayName.slice(0, 1);
    shell.querySelector(".uname").textContent = displayName;

    var menu = shell.querySelector(".user-menu");
    var dropdown = shell.querySelector(".dropdown");
    var items = '';
    if (currentUser.role === "Admin") items += '<button data-act="admin">用户管理</button>';
    items += '<button data-act="logout">退出登录</button>';
    dropdown.innerHTML = items;
    menu.addEventListener("click", function (e) {
      if (e.target.tagName === "BUTTON") {
        var act = e.target.getAttribute("data-act");
        if (act === "logout") {
          api("/auth/logout", { method: "POST" }).then(function () {
            currentUser = null; location.hash = "/login";
          });
        } else if (act === "admin") {
          location.hash = "/admin";
        } else {
          location.hash = "/home";
        }
        dropdown.style.display = "none";
        return;
      }
      dropdown.style.display = dropdown.style.display === "none" ? "block" : "none";
    });
    document.addEventListener("click", function (e) {
      if (!menu.contains(e.target)) dropdown.style.display = "none";
    });

    var cardsBox = shell.querySelector(".cards");
    app.innerHTML = "";
    app.appendChild(shell);
    cardsBox.innerHTML = '<div class="loading">加载平台列表…</div>';

    api("/platforms").then(function (list) {
      cardsBox.innerHTML = "";
      list.forEach(function (p) {
        var navItems = PLATFORM_NAV[p.id] || [];
        var navHtml = navItems.map(function (n) {
          return '<span class="pc-nav-item">' + esc(n.name) + '</span>';
        }).join("");
        var c = el(
          '<a class="platform-card ' + (p.color === "multicolor" ? "multicolor" : "") + '">' +
            '<div class="pc-head"><span class="pc-icon">' + (p.id === "compute" ? "计" : "数") + "</span>" +
              '<div class="pc-name">' + esc(p.name) + '</div></div>' +
            '<div class="pc-tags">' + navHtml + '</div>' +
            '<div class="pc-foot"><span class="pc-link">进入平台</span><span class="pc-arrow">→</span></div>' +
          "</a>"
        );
        c.addEventListener("click", function () { window.open(p.url, "_self"); });
        cardsBox.appendChild(c);
      });
    }).catch(function (err) {
      cardsBox.innerHTML = '<div class="auth-error">' + esc(err.message) + "</div>";
    });

    var demoInput = shell.querySelector(".demo-input");
    var demoGen = shell.querySelector(".demo-gen");
    var demoCopy = shell.querySelector(".demo-copy");
    demoGen.addEventListener("click", function () {
      demoGen.disabled = true; demoGen.textContent = "生成中…";
      api("/auth/demo-token", { method: "POST" }).then(function (res) {
        var base = location.pathname.replace(/[^/]*$/, "");
        demoInput.value = location.origin + base + "t/" + res.token;
        demoGen.textContent = "重新生成";
        demoGen.disabled = false;
      }).catch(function (err) {
        demoGen.textContent = "生成失败";
        setTimeout(function () { demoGen.textContent = "生成链接"; demoGen.disabled = false; }, 1500);
      });
    });
    demoCopy.addEventListener("click", function () {
      if (!demoInput.value) return;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(demoInput.value).then(function () {
          demoCopy.textContent = "已复制";
          setTimeout(function () { demoCopy.textContent = "复制链接"; }, 1500);
        });
      } else {
        demoInput.select(); document.execCommand("copy");
        demoCopy.textContent = "已复制";
        setTimeout(function () { demoCopy.textContent = "复制链接"; }, 1500);
      }
    });
  }

  /* ---------- 用户管理(Admin) ---------- */
  function renderAdmin() {
    var shell = el(
      '<div class="portal-shell">' +
        '<div class="topbar">' +
          '<div class="brand"><span class="dot">' + CLOUD_ICON + '</span>' +
            '<span class="name">云锡统一门户</span>' +
            '<span class="tag">用户管理</span></div>' +
          '<div class="user-menu"><span class="avatar"></span><span class="uname"></span>' +
            '<span class="caret">▼</span><div class="dropdown" style="display:none"></div></div>' +
        "</div>" +
        '<div class="page">' +
          '<div class="page-head"><h2>用户管理</h2><p>管理员可创建、修改或停用平台用户</p></div>' +
          '<div class="panel"><div class="toolbar"><button class="btn blue" data-act="add">+ 新建用户</button>' +
            '<button class="btn" data-act="back">返回平台入口</button></div>' +
            '<table class="grid"><thead><tr><th>ID</th><th>用户名</th><th>显示名</th>' +
            '<th>角色</th><th>邮箱</th><th>状态</th><th>创建时间</th><th>操作</th></tr></thead>' +
            '<tbody class="rows"><tr><td colspan="8" class="loading">加载中…</td></tr></tbody></table></div>' +
        "</div>" +
      "</div>"
    );

    shell.querySelector(".avatar").textContent = (currentUser.display_name || currentUser.username).slice(0, 1);
    shell.querySelector(".uname").textContent = currentUser.display_name || currentUser.username;
    var menu = shell.querySelector(".user-menu");
    var dropdown = shell.querySelector(".dropdown");
    dropdown.innerHTML = '<button data-act="admin">用户管理</button><button data-act="logout">退出登录</button>';
    menu.addEventListener("click", function (e) {
      if (e.target.tagName === "BUTTON") {
        var act = e.target.getAttribute("data-act");
        if (act === "logout") api("/auth/logout", { method: "POST" }).then(function () { currentUser = null; location.hash = "/login"; });
        else if (act === "admin") location.hash = "/admin";
        else location.hash = "/home";
        dropdown.style.display = "none"; return;
      }
      dropdown.style.display = dropdown.style.display === "none" ? "block" : "none";
    });
    document.addEventListener("click", function (e) { if (!menu.contains(e.target)) dropdown.style.display = "none"; });

    shell.querySelector('[data-act="add"]').addEventListener("click", function () { openUserModal(null); });
    shell.querySelector('[data-act="back"]').addEventListener("click", function () { location.hash = "/home"; });

    app.innerHTML = "";
    app.appendChild(shell);
    var rows = shell.querySelector(".rows");

    function load() {
      api("/users").then(function (users) {
        rows.innerHTML = "";
        users.forEach(function (u) {
          var tr = el(
            "<tr><td>" + u.id + "</td><td>" + esc(u.username) + "</td><td>" + esc(u.display_name || "") + "</td>" +
            '<td><span class="role-pill ' + u.role + '">' + u.role + "</span></td>" +
            "<td>" + esc(u.email || "-") + "</td>" +
            "<td>" + (u.disabled ? '<span class="badge-off">已停用</span>' : "正常") + "</td>" +
            "<td>" + esc((u.created_at || "").replace("T", " ").slice(0, 19)) + "</td>" +
            '<td><button class="btn" data-edit="' + u.id + '">编辑</button> ' +
            (u.username === "admin"
              ? '<button class="btn" disabled>删除</button>'
              : '<button class="btn danger" data-del="' + u.id + '">删除</button>') +
            "</td></tr>"
          );
          rows.appendChild(tr);
        });
        rows.querySelectorAll("[data-edit]").forEach(function (b) {
          b.addEventListener("click", function () {
            var id = +b.getAttribute("data-edit");
            var u = users.find(function (x) { return x.id === id; });
            openUserModal(u);
          });
        });
        rows.querySelectorAll("[data-del]").forEach(function (b) {
          b.addEventListener("click", function () {
            if (!confirm("确认删除该用户？")) return;
            api("/users/" + b.getAttribute("data-del"), { method: "DELETE" }).then(load)
              .catch(function (e) { alert(e.message); });
          });
        });
      }).catch(function (e) { rows.innerHTML = '<tr><td colspan="8" class="auth-error">' + esc(e.message) + "</td></tr>"; });
    }
    load();
  }

  function openUserModal(user) {
    var isEdit = !!user;
    var mask = el(
      '<div class="modal-mask"><div class="modal"><h3>' + (isEdit ? "编辑用户" : "新建用户") + "</h3>" +
        '<div class="msg"></div>' +
        '<div class="field"><label>用户名<span class="req">*</span></label><input name="username" ' + (isEdit ? "disabled" : "") + ' placeholder="3-50 位" /></div>' +
        '<div class="field"><label>邮箱<span class="req">*</span></label><input name="email" type="email" placeholder="example@mail.com" /></div>' +
        '<div class="field"><label>显示名称（选填）</label><input name="display" placeholder="选填" /></div>' +
        '<div class="field"><label>角色</label><select name="role"><option>Users</option><option>Admin</option></select></div>' +
        '<div class="field password-field"><label>' + (isEdit ? "重置密码（留空则不修改）" : "密码（至少 6 位）") + '</label><div class="input-box"><input name="password" type="password" placeholder="至少 6 位" />' + eyeToggleSvg() + '</div></div>' +
        (isEdit ? '<div class="field"><label><input type="checkbox" name="disabled" /> 停用该账号</label></div>' : "") +
        '<div class="modal-actions"><button class="btn" data-act="cancel">取消</button>' +
        '<button class="btn blue" data-act="save">' + (isEdit ? "保存" : "创建") + "</button></div>" +
      "</div></div>"
    );
    var form = mask.querySelector(".modal");
    if (isEdit) {
      form.username.value = user.username;
      form.email.value = user.email || "";
      form.display.value = user.display_name || "";
      form.role.value = user.role;
      form.disabled.checked = user.disabled;
    }
    mask.addEventListener("click", function (e) {
      if (e.target === mask || e.target.getAttribute("data-act") === "cancel") mask.remove();
    });
    form.querySelector('[data-act="save"]').addEventListener("click", function () {
      var msg = mask.querySelector(".msg");
      msg.innerHTML = "";
      var email = (form.email.value || "").trim();
      if (!email) {
        msg.innerHTML = '<div class="auth-error">请填写邮箱</div>';
        return;
      }
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        msg.innerHTML = '<div class="auth-error">邮箱格式不正确</div>';
        return;
      }
      var payload = {
        display_name: form.display.value.trim() || null,
        role: form.role.value,
        email: email,
      };
      if (form.password.value) payload.password = form.password.value;
      if (isEdit) payload.disabled = form.disabled.checked;
      else payload.username = form.username.value.trim();
      var req;
      if (isEdit) req = api("/users/" + user.id, { method: "PUT", body: JSON.stringify(payload) });
      else req = api("/users", { method: "POST", body: JSON.stringify(payload) });
      req.then(function () { mask.remove(); location.reload(); })
        .catch(function (e) { msg.innerHTML = '<div class="auth-error">' + esc(e.message) + "</div>"; });
    });
    document.body.appendChild(mask);
  }

  window.addEventListener("hashchange", route);
  route();
})();