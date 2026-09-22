#!/usr/bin/env python3
"""
HTTP 抽象层：优先使用 requests，不可用时回退到 urllib。

Public API:
    HAS_REQUESTS   — 是否安装了 requests 库
    build_session() — 构建带认证信息的 HTTP session
"""

import json

# ---------------------------------------------------------------------------
# HTTP 抽象层：优先使用 requests，不可用时回退到 urllib
# ---------------------------------------------------------------------------

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    import urllib.request
    import urllib.error
    import urllib.parse
    import ssl


def build_session(args):
    """构建 HTTP session，注入认证信息（cookie / csrf token）"""
    if HAS_REQUESTS:
        session = requests.Session()
        session.verify = False  # 内网环境通常自签证书
        headers = {
            "Accept": "application/json",
        }
        # CSRF token 处理
        csrf = getattr(args, "csrf", None) or getattr(args, "csrf_token", None)
        if csrf:
            headers["X-Cf-Random"] = csrf
            headers["_csrf_"] = csrf
        # Cookie 处理
        cookie = getattr(args, "cookie", None)
        if cookie:
            headers["Cookie"] = cookie
        session.headers.update(headers)
        return session
    else:
        # urllib 回退：返回一个简易包装对象
        return _UrllibSession(args)


class _UrllibSession:
    """当 requests 不可用时的 urllib 简易 session 封装"""

    def __init__(self, args):
        self.headers = {
            "Accept": "application/json",
        }
        csrf = getattr(args, "csrf", None) or getattr(args, "csrf_token", None)
        if csrf:
            self.headers["X-Cf-Random"] = csrf
            self.headers["_csrf_"] = csrf
        cookie = getattr(args, "cookie", None)
        if cookie:
            self.headers["Cookie"] = cookie
        # 忽略 SSL 验证
        self._ctx = ssl.create_default_context()
        self._ctx.check_hostname = False
        self._ctx.verify_mode = ssl.CERT_NONE

    def get(self, url, params=None, timeout=30):
        if params:
            qs = urllib.parse.urlencode(params, doseq=True)
            url = f"{url}?{qs}"
        req = urllib.request.Request(url, headers=self.headers, method="GET")
        try:
            resp = urllib.request.urlopen(req, timeout=timeout, context=self._ctx)
            body = resp.read().decode("utf-8")
            return _UrllibResponse(resp.status, body)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            return _UrllibResponse(e.code, body)
        except Exception as e:
            return _UrllibResponse(0, str(e))

    def post(self, url, **kwargs):
        timeout = kwargs.pop('timeout', 30)
        json_data = kwargs.pop('json', kwargs.pop('json_data', None))
        form_data = kwargs.pop('data', None)
        headers = dict(self.headers)
        if json_data is not None:
            data = _json_dumps_bytes(json_data)
            headers["Content-Type"] = "application/json"
        elif isinstance(form_data, dict):
            data = urllib.parse.urlencode(form_data).encode("utf-8")
            headers["Content-Type"] = (
                "application/x-www-form-urlencoded;charset=UTF-8"
            )
        elif form_data is not None:
            data = (
                form_data.encode("utf-8")
                if isinstance(form_data, str)
                else form_data
            )
        else:
            data = None
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            resp = urllib.request.urlopen(req, timeout=timeout, context=self._ctx)
            body = resp.read().decode("utf-8")
            return _UrllibResponse(resp.status, body)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            return _UrllibResponse(e.code, body)
        except Exception as e:
            return _UrllibResponse(0, str(e))


def _json_dumps_bytes(obj):
    return json.dumps(obj).encode("utf-8")


class _UrllibResponse:
    """urllib 响应包装，提供与 requests.Response 类似的接口"""

    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text
        self.ok = 200 <= status_code < 300

    def json(self):
        return json.loads(self.text)
