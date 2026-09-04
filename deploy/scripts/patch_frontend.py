#!/usr/bin/env python3
"""云锡平台前端子路径化补丁（幂等、带断言防漂移）。

在源码树副本上执行：把三前端从「根路径部署」改造为：
  portal  → /yunxi/        （hash 路由，改相对资源引用 + 同 host redirect 白名单）
  compute → /yunxi/compute/（vite base + router base + PORTAL_LOGIN + API 前缀）
  data    → /yunxi/data/   （同上 + 交付物下载直链）

用法：python3 patch_frontend.py <项目根>
"""
import re
import sys
from pathlib import Path


def die(msg: str) -> None:
    print(f"[patch] FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def sub_once(content: str, pattern: str, repl: str, where: str, count: int = 1) -> str:
    new, n = re.subn(pattern, repl, content, count=count)
    if n != count:
        die(f"{where}: 预期替换 {count} 处，实际 {n} 处（源码结构已漂移，请人工核对 pattern: {pattern}）")
    return new


def patch_portal(root: Path) -> None:
    idx = root / "portal" / "static" / "index.html"
    html = idx.read_text(encoding="utf-8")
    if 'href="/assets/style.css"' in html:
        html = sub_once(html, r'href="/assets/style\.css"', 'href="assets/style.css"', str(idx))
        html = sub_once(html, r'src="/assets/app\.js"', 'src="assets/app.js"', str(idx))
        idx.write_text(html, encoding="utf-8")
        print("[patch] portal/static/index.html: 资源引用 → 相对路径")
    else:
        print("[patch] portal index.html: 已是相对路径，跳过")

    js = root / "portal" / "static" / "assets" / "app.js"
    code = js.read_text(encoding="utf-8")
    old_line = '  var API = "/api/v1";'
    if old_line in code:
        if code.count(old_line) != 1:
            die(f"{js}: var API 行匹配数 != 1（源码漂移）")
        new_line = '  var API = location.pathname.replace(/[^/]*$/, "") + "api/v1";'
        code = code.replace(old_line, new_line)
        js.write_text(code, encoding="utf-8")
        print("[patch] portal app.js: API 前缀 → pathname 动态推导（子路径/根路径双兼容）")

    old_line = "if (p && /^https?:\\/\\/(localhost|127\\.0\\.0\\.1)(:|\\/|$)/i.test(p)) return p;"
    if "localhost|127" in code and "location.host" not in code:
        if code.count(old_line) != 1:
            die(f"{js}: redirect 白名单行匹配数 != 1（源码漂移）")
        new_line = "if (p && (function(u){ try { return new URL(u).host === location.host; } catch(e) { return false; } })(p)) return p;"
        code = code.replace(old_line, new_line)
        js.write_text(code, encoding="utf-8")
        print("[patch] portal app.js: redirect 白名单 → 同 host 校验")
    else:
        print("[patch] portal app.js: redirect 白名单已是同 host 或已改，跳过")


def _sub_portal_login_js(path: Path, base: str) -> None:
    code = path.read_text(encoding="utf-8")
    if "http://localhost:8003" in code:
        code = sub_once(code, r"const PORTAL_LOGIN = 'http://localhost:8003/'", f"const PORTAL_LOGIN = '{base}'", str(path))
        path.write_text(code, encoding="utf-8")
        print(f"[patch] {path.relative_to(path.parents[3])}: PORTAL_LOGIN → {base}")
    else:
        print(f"[patch] {path.name}: PORTAL_LOGIN 已改，跳过")


def _patch_app_vue(path: Path, base: str) -> None:
    code = path.read_text(encoding="utf-8")
    if "http://localhost:8003" in code:
        code = sub_once(code, r"window\.location\.href = 'http://localhost:8003/#/home'", f"window.location.href = '{base}#/home'", str(path))
        code = sub_once(code, r"window\.location\.href = 'http://localhost:8003'", f"window.location.href = '{base}'", str(path))
        path.write_text(code, encoding="utf-8")
        print(f"[patch] {path.relative_to(path.parents[3])}: 门户跳转 → {base}")
    else:
        print(f"[patch] {path.name}: 门户跳转已改，跳过")


def _patch_app_vue_manual(path: Path, api_base: str) -> None:
    code = path.read_text(encoding="utf-8")
    if "a.href = '/api/v1/manual'" in code:
        code = sub_once(code, r"a\.href = '/api/v1/manual'", f"a.href = '{api_base}/manual'", str(path))
        path.write_text(code, encoding="utf-8")
        script_rel = "/".join(path.parts[-4:])
        print(f"[patch] {script_rel}: manual 直链 → {api_base}/manual")
    else:
        print(f"[patch] {path.name}: manual 直链已改，跳过")


def _sub_api_prefix_js(path: Path) -> None:
    code = path.read_text(encoding="utf-8")
    for quote in ("'", '"'):
        old = f"const API_BASE_URL = {quote}/api/v1{quote}"
        if old in code:
            sub_once(code, re.escape(old), "const API_BASE_URL = import.meta.env.BASE_URL + 'api/v1'", str(path), 0) if False else None
            if code.count(old) != 1:
                die(f"{path.name}: {old} 匹配数 != 1（源码漂移）")
            code = code.replace(old, "const API_BASE_URL = import.meta.env.BASE_URL + 'api/v1'")
            path.write_text(code, encoding="utf-8")
            print(f"[patch] {path.name}: API_BASE_URL → BASE_URL 拼接")
            return
    if "import.meta.env.BASE_URL" in code:
        print(f"[patch] {path.name}: API_BASE_URL 已改，跳过")
    else:
        die(f"{path.name}: 未找到 API_BASE_URL 定义（漂移）")


def _sub_api_prefix_ts(path: Path) -> None:
    code = path.read_text(encoding="utf-8")
    if "baseURL: '/api/v1'" in code:
        code = sub_once(code, r"baseURL: '/api/v1'", "baseURL: import.meta.env.BASE_URL + 'api/v1'", str(path))
        path.write_text(code, encoding="utf-8")
        print(f"[patch] {path.name}: baseURL → BASE_URL 拼接")
    else:
        print(f"[patch] {path.name}: baseURL 已改，跳过")


def _patch_role(path: Path) -> None:
    code = path.read_text(encoding="utf-8")
    if "axios.get('/api/v1/me')" in code:
        code = sub_once(code, r"axios\.get\('/api/v1/me'\)", "axios.get(import.meta.env.BASE_URL + 'api/v1/me')", str(path))
        path.write_text(code, encoding="utf-8")
        print(f"[patch] {path.name}: /me 请求 → BASE_URL 拼接")
    else:
        print(f"[patch] {path.name}: /me 已改，跳过")


def _patch_profile(path: Path) -> None:
    code = path.read_text(encoding="utf-8")
    changed = False
    if "axios.put('/api/v1/user/profile'" in code:
        code = sub_once(code, r"axios\.put\('/api/v1/user/profile'", "axios.put(import.meta.env.BASE_URL + 'api/v1/user/profile'", str(path))
        changed = True
    if "axios.get('/api/v1/user/profile'" in code:
        code = sub_once(code, r"axios\.get\('/api/v1/user/profile'", "axios.get(import.meta.env.BASE_URL + 'api/v1/user/profile'", str(path))
        changed = True
    if changed:
        path.write_text(code, encoding="utf-8")
        print(f"[patch] {path.name}: profile 请求 → BASE_URL 拼接")
    else:
        print(f"[patch] {path.name}: profile 请求已改/无硬编码，跳过")


def patch_compute(root: Path, base: str) -> None:
    fe = root / "platforms" / "compute" / "frontend"
    vc = fe / "vite.config.js"
    code = vc.read_text(encoding="utf-8")
    if "base:" not in code:
        code = sub_once(code, r"export default defineConfig\(\{\n", "export default defineConfig({\n  base: '/yunxi/compute/',\n", str(vc))
        vc.write_text(code, encoding="utf-8")
        print("[patch] compute vite.config.js: base 已设")
    else:
        print("[patch] compute vite.config.js: base 已存在，跳过")

    router = fe / "src" / "router" / "index.js"
    code = router.read_text(encoding="utf-8")
    if "createWebHistory()" in code:
        code = sub_once(code, r"createWebHistory\(\)", "createWebHistory(import.meta.env.BASE_URL)", str(router))
        router.write_text(code, encoding="utf-8")
        print("[patch] compute router: base 已设")
    else:
        print("[patch] compute router: 已改，跳过")

    _sub_portal_login_js(fe / "src" / "main.js", "/yunxi/")
    _patch_app_vue(fe / "src" / "App.vue", "/yunxi/")
    _patch_app_vue_manual(fe / "src" / "App.vue", base + "api/v1")
    for name in ("DataPlatform.vue", "Reasoning.vue", "ReasoningV3.vue", "Records.vue"):
        _sub_api_prefix_js(fe / "src" / "views" / name)
    _patch_role(fe / "src" / "role.js")
    _patch_profile(fe / "src" / "views" / "ProfilePage.vue")


def patch_data(root: Path, base: str) -> None:
    fe = root / "platforms" / "data" / "frontend"
    vc = fe / "vite.config.ts"
    code = vc.read_text(encoding="utf-8")
    if "base:" not in code:
        code = sub_once(code, r"export default defineConfig\(\{\n", "export default defineConfig({\n  base: '/yunxi/data/',\n", str(vc))
        vc.write_text(code, encoding="utf-8")
        print("[patch] data vite.config.ts: base 已设")
    else:
        print("[patch] data vite.config.ts: base 已存在，跳过")

    router = fe / "src" / "router.ts"
    code = router.read_text(encoding="utf-8")
    if "createWebHistory()" in code:
        code = sub_once(code, r"createWebHistory\(\)", "createWebHistory(import.meta.env.BASE_URL)", str(router))
        router.write_text(code, encoding="utf-8")
        print("[patch] data router: base 已设")
    else:
        print("[patch] data frontend router: 已改，跳过")

    api = fe / "src" / "services" / "api.ts"
    _sub_portal_login_js(api, "/yunxi/")
    _sub_api_prefix_ts(api)
    code = api.read_text(encoding="utf-8")
    if "return '/api/v1/pipeline/artifacts/latest-delivery/download'" in code:
        code = sub_once(code, r"return '/api/v1/pipeline/artifacts/latest-delivery/download'", "return import.meta.env.BASE_URL + 'api/v1/pipeline/artifacts/latest-delivery/download'", str(api))
        api.write_text(code, encoding="utf-8")
        print("[patch] data api.ts: 交付物下载直链 → BASE_URL 拼接")
    else:
        print("[patch] data api.ts: 下载直链已改，跳过")

    _patch_app_vue(fe / "src" / "App.vue", "/yunxi/")
    _patch_app_vue_manual(fe / "src" / "App.vue", base + "api/v1")
    _patch_role(fe / "src" / "role.ts")
    _patch_profile(fe / "src" / "views" / "ProfilePage.vue")


def main() -> None:
    if len(sys.argv) != 2:
        die(f"用法: {sys.argv[0]} <项目根>")
    root = Path(sys.argv[1]).resolve()
    if not (root / "portal" / "run_portal.py").exists():
        die(f"不是云锡项目根: {root}")
    patch_portal(root)
    patch_compute(root, "/yunxi/compute/")
    patch_data(root, "/yunxi/data/")
    print("[patch] 全部补丁应用完成")


if __name__ == "__main__":
    main()
