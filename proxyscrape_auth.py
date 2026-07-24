"""
ProxyScrape Dashboard 认证自动化骨架
逆向自 dashboard.proxyscrape.com/v2 的 webpack 运行时模块

三条登录路径：
  1. 密码登录 — 需要 Turnstile token
  2. OTP 魔法链接 — 不需要 Turnstile（最轻路径）
  3. Google OAuth — 需要 Turnstile + Google ID Token

所有 auth 端点统一用 application/x-www-form-urlencoded POST，
响应格式 {"userData": {...}, "access_token": "..."}
"""

import json
import time
import base64
import requests
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


BASE = "https://dashboard.proxyscrape.com"
TOKEN_FILE = Path("proxyscrape_token.json")

# 从 webpack module 84194 提取的端点配置
ENDPOINTS = {
    "login":                f"{BASE}/v2/v4/account/auth/login",
    "register":             f"{BASE}/v2/v4/account/auth/register",
    "logout":               f"{BASE}/v2/v4/account/auth/logout",
    "me":                   f"{BASE}/v2/v4/account/auth/me",
    "refresh":              f"{BASE}/v2/v4/account/auth/refresh",
    "send_reset_link":      f"{BASE}/v2/v4/account/auth/send-password-reset-link",
    "reset_password":       f"{BASE}/v2/v4/account/auth/reset-password",
    "verify_email":         f"{BASE}/v2/v4/account/verify-email",
    "resend_verification":  f"{BASE}/v2/v4/account/reset-verification-code",
    "init":                 f"{BASE}/v2/api/init",
}

# Turnstile sitekey（如需浏览器端过验证）
TURNSTILE_SITEKEY = "0x4AAAAAAAFWUVCKyusT9T8r"
# Google OAuth client ID
GOOGLE_CLIENT_ID = "927266137698-kt67e9ai3f4oug4nakpuue8tlfvtlbhg.apps.googleusercontent.com"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "Origin": BASE,
    "Referer": f"{BASE}/v2/login",
}


@dataclass
class TokenStore:
    """镜像前端 localStorage 的 token 管理"""
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    user_data: Optional[dict] = field(default_factory=dict)

    def save(self, path: Path = TOKEN_FILE):
        path.write_text(json.dumps({
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "user_data": self.user_data,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path = TOKEN_FILE) -> "TokenStore":
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(**data)

    def clear(self):
        self.access_token = None
        self.refresh_token = None
        self.user_data = {}
        if TOKEN_FILE.exists():
            TOKEN_FILE.unlink()

    @property
    def bearer(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"} if self.access_token else {}


class ProxyScrapeAuth:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.tokens = TokenStore.load()

    # ── 核心：处理 auth 响应 ──────────────────────────────
    def _handle_auth_response(self, resp: requests.Response) -> dict:
        """统一处理 login/register 的响应，存 token"""
        resp.raise_for_status()
        data = resp.json()
        if "access_token" in data:
            self.tokens.access_token = data["access_token"]
            self.tokens.user_data = data.get("userData", {})
            self.tokens.save()
            print(f"[+] 登录成功，用户: {self.tokens.user_data.get('email', '?')}")
        else:
            print(f"[!] 响应无 access_token: {data}")
        return data

    # ── 路径 1：密码登录（需 Turnstile）─────────────────────
    def login_password(self, email: str, password: str, turnstile_token: str) -> dict:
        """
        密码登录。turnstile_token 需要你自己解决：
        - 手动从浏览器 DevTools 抓（Network 面板看 cf-turnstile-response）
        - 或接第三方打码平台（CapSolver / 2Captcha 等支持 Turnstile）
        - 或用 playwright/selenium 加载真实页面让它自动过
        """
        resp = self.session.post(ENDPOINTS["login"], data={
            "email": email,
            "password": password,
            "cf_turnstile_token": turnstile_token,
        })
        return self._handle_auth_response(resp)

    # ── 路径 2：OTP 登录（免 Turnstile，最轻路径）────────────
    def login_otp(self, email: str, otp: str) -> dict:
        """
        OTP 魔法链接登录 — 不需要 Turnstile。
        邮件里的链接格式：/v2/login?email=<base64>&otp=<code>
        前端 atob(email) 后和 otp 一起 POST。
        """
        resp = self.session.post(ENDPOINTS["login"], data={
            "email": email,
            "otp": otp,
        })
        return self._handle_auth_response(resp)

    @staticmethod
    def parse_otp_link(url: str) -> tuple[str, str]:
        """从魔法链接 URL 解析出 email 和 otp"""
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(url).query)
        email_b64 = qs.get("email", [""])[0]
        otp = qs.get("otp", [""])[0]
        email = base64.b64decode(email_b64).decode()
        return email, otp

    # ── 路径 3：Google OAuth 登录 ──────────────────────────
    def login_google(self, google_id_token: str, turnstile_token: str) -> dict:
        """
        Google 登录。credential 是 Google Sign-In 返回的 ID Token（JWT）。
        前端用 jwt-decode 从中取 email。
        如果返回 401，前端判定为账号不存在，跳注册。
        """
        import jwt as pyjwt  # pip install pyjwt
        payload = pyjwt.decode(google_id_token, options={"verify_signature": False})
        email = payload.get("email", "")

        resp = self.session.post(ENDPOINTS["login"], data={
            "service": "google",
            "email": email,
            "cf_turnstile_token": turnstile_token,
            "credential": google_id_token,
        })
        if resp.status_code == 401:
            print("[*] 账号不存在，尝试自动注册...")
            return self.register_google(google_id_token, turnstile_token)
        return self._handle_auth_response(resp)

    # ── 注册（邮箱）────────────────────────────────────────
    def register_email(self, email: str, password: str, turnstile_token: str) -> dict:
        """
        邮箱注册。confirm_password 和 terms 勾选只做前端校验，不进 payload。
        注册成功后需要走 verify_email 做邮箱验证。
        """
        resp = self.session.post(ENDPOINTS["register"], data={
            "email": email,
            "password": password,
            "cf_turnstile_token": turnstile_token,
        })
        return self._handle_auth_response(resp)

    # ── 注册（Google）──────────────────────────────────────
    def register_google(self, google_id_token: str, turnstile_token: str) -> dict:
        """
        Google 注册。如果返回 error=="account_exists"，
        前端自动回退到 login_google。
        """
        import jwt as pyjwt
        payload = pyjwt.decode(google_id_token, options={"verify_signature": False})
        email = payload.get("email", "")

        resp = self.session.post(ENDPOINTS["register"], data={
            "service": "google",
            "email": email,
            "cf_turnstile_token": turnstile_token,
            "credential": google_id_token,
        })
        data = resp.json()
        if data.get("error") == "account_exists":
            print("[*] 账号已存在，回退到登录...")
            return self.login_google(google_id_token, turnstile_token)
        return self._handle_auth_response(resp)

    # ── 会话管理 ───────────────────────────────────────────
    def me(self) -> Optional[dict]:
        """
        POST /auth/me 拉当前用户信息。
        前端启动时用这个判断 token 是否有效。
        """
        if not self.tokens.access_token:
            return None
        resp = self.session.post(
            ENDPOINTS["me"],
            headers=self.tokens.bearer,
        )
        if resp.ok:
            data = resp.json()
            self.tokens.user_data = data
            return data
        print(f"[!] /me 失败 ({resp.status_code})，token 可能过期")
        return None

    def refresh(self) -> bool:
        """刷新 token（前端配置 onTokenExpiration: "refreshToken"）"""
        if not self.tokens.refresh_token:
            print("[!] 无 refresh_token，需重新登录")
            return False
        resp = self.session.post(
            ENDPOINTS["refresh"],
            headers=self.tokens.bearer,
            data={"refresh_token": self.tokens.refresh_token},
        )
        if resp.ok:
            data = resp.json()
            if "access_token" in data:
                self.tokens.access_token = data["access_token"]
                self.tokens.save()
                print("[+] Token 已刷新")
                return True
        print(f"[!] 刷新失败 ({resp.status_code})")
        return False

    def logout(self):
        """登出并清空本地 token"""
        if self.tokens.access_token:
            self.session.post(ENDPOINTS["logout"], headers=self.tokens.bearer)
        self.tokens.clear()
        print("[+] 已登出")

    # ── 邮箱验证 ───────────────────────────────────────────
    def verify_email(self, code: str) -> dict:
        """注册后的邮箱验证码校验"""
        resp = self.session.post(
            ENDPOINTS["verify_email"],
            headers=self.tokens.bearer,
            data={"code": code},
        )
        resp.raise_for_status()
        return resp.json()

    def resend_verification(self) -> dict:
        """重发邮箱验证码"""
        resp = self.session.post(
            ENDPOINTS["resend_verification"],
            headers=self.tokens.bearer,
        )
        resp.raise_for_status()
        return resp.json()

    # ── 密码重置 ───────────────────────────────────────────
    def send_reset_link(self, email: str) -> dict:
        resp = self.session.post(
            ENDPOINTS["send_reset_link"],
            data={"email": email},
        )
        resp.raise_for_status()
        return resp.json()

    def reset_password(self, token: str, password: str) -> dict:
        resp = self.session.post(
            ENDPOINTS["reset_password"],
            data={"token": token, "password": password},
        )
        resp.raise_for_status()
        return resp.json()

    # ── 带 token 的通用请求 ────────────────────────────────
    def authed_get(self, url: str, **kwargs) -> requests.Response:
        """带 Bearer token 的 GET，token 过期自动刷新重试一次"""
        resp = self.session.get(url, headers=self.tokens.bearer, **kwargs)
        if resp.status_code == 401 and self.refresh():
            resp = self.session.get(url, headers=self.tokens.bearer, **kwargs)
        return resp

    def authed_post(self, url: str, **kwargs) -> requests.Response:
        """带 Bearer token 的 POST，token 过期自动刷新重试一次"""
        resp = self.session.post(url, headers=self.tokens.bearer, **kwargs)
        if resp.status_code == 401 and self.refresh():
            resp = self.session.post(url, headers=self.tokens.bearer, **kwargs)
        return resp

    def get_account_overview(self, account_id: str) -> dict:
        """拉账户总览（需要从 userData 里取 AccountID）"""
        url = f"{BASE}/v2/v4/account/{account_id}/services/overview"
        return self.authed_get(url).json()


# ── 使用示例 ─────────────────────────────────────────────
if __name__ == "__main__":
    auth = ProxyScrapeAuth()

    # 先试本地 token 是否还活着
    user = auth.me()
    if user:
        print(f"[*] 已有有效会话: {user.get('email')}")
    else:
        # ── 方式 A：OTP 登录（最简单，不需要过 Turnstile）──
        # 从邮件里的魔法链接解析 email 和 otp：
        # email, otp = auth.parse_otp_link("https://dashboard.proxyscrape.com/v2/login?email=dGVzdEBleGFtcGxlLmNvbQ==&otp=123456")
        # auth.login_otp(email, otp)

        # ── 方式 B：密码登录 ──
        # turnstile_token = "从浏览器或打码平台获取"
        # auth.login_password("you@example.com", "YourPass123", turnstile_token)

        # ── 方式 C：注册新账号 ──
        # auth.register_email("new@example.com", "StrongPass123", turnstile_token)
        # auth.verify_email("验证码")

        pass

    # 登录后拉账户信息
    if auth.tokens.user_data:
        account_id = auth.tokens.user_data.get("AccountID")
        if account_id:
            overview = auth.get_account_overview(account_id)
            print(json.dumps(overview, indent=2, ensure_ascii=False))
