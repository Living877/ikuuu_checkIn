# -*- coding: utf-8 -*-
"""
iKuuu 登录辅助工具（本地运行）
用途：
当站点开启图片点选/滑动验证码等强风控时，无头自动化往往难以稳定通过。
本工具在本地启动真实浏览器（有头模式），自动预填账号密码，
由人工在桌面窗口中完成一次图片点选验证，脚本自动抓取并导出长期有效的登录 Cookie。
支持：
1. 桌面弹出真实浏览器，自动填好账号密码
2. 自动捕获登录成功的完整 Cookie
3. 本地验证 Cookie 有效性并预览流量数据
4. （可选）一键加密同步至 GitHub Actions Secrets (IKUUU_COOKIE)
"""

import os
import sys
import time
import base64
import requests
from playwright.sync_api import sync_playwright

try:
    from nacl import encoding, public
    HAS_NACL = True
except ImportError:
    HAS_NACL = False

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/120.0.0.0 Safari/537.36'
)

def format_cookies(cookies_list):
    """将 Playwright cookies 列表格式化为标准的 Cookie 请求头字符串"""
    parts = []
    for c in cookies_list:
        name = c.get('name')
        val = c.get('value')
        if name and val:
            parts.append(f"{name}={val}")
    return "; ".join(parts)

def upload_secret_to_github(repo, token, secret_name, secret_value):
    """自动使用公钥加密并将 Secret 同步至 GitHub Actions"""
    if not HAS_NACL:
        print("[!] 未安装 PyNaCl，跳过自动同步 GitHub Secrets")
        return False
    try:
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        # 1. 获取公钥
        pk_url = f"https://api.github.com/repos/{repo}/actions/secrets/public-key"
        r = requests.get(pk_url, headers=headers, timeout=10)
        r.raise_for_status()
        pk_info = r.json()

        # 2. 加密
        public_key = public.PublicKey(pk_info["key"].encode("utf-8"), encoding.Base64Encoder())
        sealed_box = public.SealedBox(public_key)
        encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
        encrypted_b64 = base64.b64encode(encrypted).decode("utf-8")

        # 3. 写入 Secret
        set_url = f"https://api.github.com/repos/{repo}/actions/secrets/{secret_name}"
        payload = {
            "encrypted_value": encrypted_b64,
            "key_id": pk_info["key_id"]
        }
        r_put = requests.put(set_url, json=payload, headers=headers, timeout=10)
        r_put.raise_for_status()
        print(f"🎉 成功同步 Secret [{secret_name}] 至 GitHub 仓库 {repo}！")
        return True
    except Exception as e:
        print(f"⚠️ 同步 GitHub Secret 失败: {e}")
        return False

def interactive_login(email=None, passwd=None, base_url="https://ikuuu.top", gh_token=None, gh_repo="995william/ikuuu_checkIn"):
    email = email or os.environ.get('IKUUU_EMAIL') or ''
    passwd = passwd or os.environ.get('IKUUU_PASSWORD') or ''
    gh_token = gh_token or os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_PAT') or ''

    print("=" * 60)
    print("🚀 iKuuu 桌面端辅助登录工具启动")
    print("=" * 60)
    print(f"目标站点: {base_url}")
    print(f"账号: {email or '（未指定，可在浏览器中手动输入）'}")
    print("正在启动本地浏览器，请在弹出的浏览器窗口中完成图片验证...")
    print("=" * 60)

    login_url = f"{base_url.rstrip('/')}/auth/login"
    cookie_str = ""

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=['--disable-blink-features=AutomationControlled']
        )
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 850},
            locale="zh-CN"
        )
        page = context.new_page()

        try:
            page.goto(login_url, wait_until='networkidle')
            if email:
                page.fill('#email', email)
            if passwd:
                page.fill('#password', passwd)
            if email and passwd:
                print("💡 账号与密码已自动填入！")
            else:
                print("💡 请在页面上输入账号密码")
            print("👉 请在弹出的浏览器窗口中点击【验证按钮】并完成图片验证，然后点击登录。")
            print("⏳ 脚本正在等待登录完成（最长等待 120 秒）...\n")

            # 等待进入 /user 页面
            page.wait_for_url("**/user**", timeout=120000)
            print("🎉 检测到已成功登录进入用户中心！")
            time.sleep(2)

            pw_cookies = context.cookies()
            cookie_str = format_cookies(pw_cookies)

            # 过滤并保存
            out_file = os.path.join(os.path.dirname(__file__), "local_cookie.txt")
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(cookie_str)
            print(f"✅ 登录 Cookie 已成功保存至本地文件: {out_file}")

            # 打印 Cookie 预览（脱敏展示）
            masked_preview = cookie_str[:25] + "******" if len(cookie_str) > 30 else "***"
            print(f"\n📋 Cookie 内容预览: {masked_preview} (总长度: {len(cookie_str)})")

            # 如果提供了 GitHub Token，自动同步
            if gh_token:
                upload_secret_to_github(gh_repo, gh_token, "IKUUU_COOKIE", cookie_str)

        except Exception as e:
            print(f"❌ 登录等待超时或出错: {e}")
        finally:
            browser.close()

    return cookie_str

if __name__ == "__main__":
    test_email = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('IKUUU_EMAIL')
    test_pwd = sys.argv[2] if len(sys.argv) > 2 else os.environ.get('IKUUU_PASSWORD')
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_PAT")
    interactive_login(test_email, test_pwd, gh_token=token)
