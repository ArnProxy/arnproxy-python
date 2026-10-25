"""ARNPROXY thin client 1.1.0. No redirects, retries, automatic polling or logging."""
from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import json
import re
import ssl
import time
from pathlib import Path
from urllib.parse import urlencode

_ROOT = Path(__file__).resolve().parent
_RESOURCES = json.loads((_ROOT / "resources.json").read_text(encoding="utf-8"))["resources"]
_MAX = 2 * 1024 * 1024


class ArnproxyError(Exception):
    def __init__(self, code, http_status=None, request_id=None, retry_after=None, uncertain=False):
        super().__init__(code)
        self.code, self.http_status, self.request_id = code, http_status, request_id
        self.retry_after, self.uncertain = retry_after, uncertain


class Client:
    BASE = "https://www.arnproxy.com/account/api/v1/"

    def __init__(self, api_key: str, *, allow_writes=False, allow_provider_reads=False, timeout=20):
        if not isinstance(api_key, str) or not re.fullmatch(r"(?:[A-Za-z0-9]{32}|arnp_[a-f0-9]{16}_[a-f0-9]{64})", api_key):
            raise ArnproxyError("INVALID_KEY_FORMAT")
        if type(allow_writes) is not bool or type(allow_provider_reads) is not bool or type(timeout) not in (int, float) or not 1 <= timeout <= 60:
            raise ArnproxyError("INVALID_CLIENT_OPTIONS")
        self.__api_key = api_key
        self.allow_writes, self.allow_provider_reads, self.timeout = allow_writes, allow_provider_reads, timeout

    def __repr__(self):
        return "<ArnproxyClient key=REDACTED>"

    def __getstate__(self):
        raise ArnproxyError("SERIALIZATION_DISABLED")

    def account(self):
        return self.request("account")

    def capabilities(self):
        return self.request("capabilities")

    def request(self, resource: str, params: dict | None = None, *, operation_key: str | None = None):
        spec = _RESOURCES.get(resource) if isinstance(resource, str) else None
        if spec is None:
            raise ArnproxyError("UNKNOWN_RESOURCE")
        if params is None:
            params = {}
        if type(params) is not dict or any(type(k) is not str for k in params) or "resource" in params:
            raise ArnproxyError("INVALID_PARAMETERS")
        params = dict(params)
        if spec["disabled"]:
            raise ArnproxyError("DISABLED_RESOURCE")
        write = spec["write"]
        if write and self.allow_writes is not True:
            raise ArnproxyError("WRITES_DISABLED")
        if spec["provider_read"] and self.allow_provider_reads is not True:
            raise ArnproxyError("PROVIDER_READS_DISABLED")
        headers = {"Authorization": "Bearer " + self.__api_key, "Accept": "application/json", "User-Agent": "ARNPROXY-Python/1.1.0"}
        if spec["idempotency"]:
            if not isinstance(operation_key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,100}", operation_key):
                raise ArnproxyError("OPERATION_KEY_REQUIRED")
            headers["Idempotency-Key"] = operation_key
        elif operation_key is not None:
            raise ArnproxyError("UNEXPECTED_OPERATION_KEY")
        path = spec["path"]
        if "{id}" in path:
            value = params.pop("id", None)
            if type(value) not in (int, str) or not re.fullmatch(r"[1-9][0-9]{0,9}", str(value)) or int(value) > 2147483647:
                raise ArnproxyError("INVALID_ROUTE_ID")
            path = path.replace("{id}", str(value))
        body = None
        if spec["method"] == "GET":
            query = []
            for k, v in params.items():
                if type(v) not in (str, int, bool):
                    raise ArnproxyError("INVALID_QUERY_VALUE")
                query.append((k, "1" if v is True else "0" if v is False else str(v)))
            if query:
                path += "?" + urlencode(query)
        else:
            try:
                body = json.dumps(params, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
            except (TypeError, ValueError, OverflowError, UnicodeError, RecursionError):
                raise ArnproxyError("INVALID_JSON_BODY") from None
            if len(body) > _MAX:
                raise ArnproxyError("REQUEST_TOO_LARGE")
            headers["Content-Type"] = "application/json"
        try:
            status, response_headers, raw = self._send(spec["method"], "/account/api/v1/" + path, headers, body)
        except ArnproxyError as exc:
            raise ArnproxyError(exc.code, uncertain=write) from None
        except Exception:
            raise ArnproxyError("TRANSPORT_ERROR", uncertain=write) from None
        if 300 <= status < 400:
            raise ArnproxyError("REDIRECT_BLOCKED", http_status=status, uncertain=write)
        retry = response_headers.get("retry-after", "")
        retry = int(retry) if isinstance(retry, str) and re.fullmatch(r"[0-9]{1,5}", retry) and int(retry) <= 86400 else None
        if not isinstance(raw, bytes) or len(raw) > _MAX:
            raise ArnproxyError("RESPONSE_TOO_LARGE", http_status=status, uncertain=write)
        try:
            result = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeError, RecursionError):
            raise ArnproxyError("INVALID_API_RESPONSE", http_status=status, retry_after=retry, uncertain=write)
        request_id = result.get("meta", {}).get("request_id") if type(result) is dict and type(result.get("meta")) is dict else None
        if not isinstance(request_id, str) or not re.fullmatch(r"[a-f0-9]{24}", request_id):
            request_id = None
        if type(result) is not dict or type(result.get("ok")) is not bool or request_id is None:
            raise ArnproxyError("INVALID_API_RESPONSE", http_status=status, retry_after=retry, uncertain=write)
        if not 200 <= status < 300 or result["ok"] is not True:
            error = result.get("error")
            code = error.get("code") if type(error) is dict else None
            if not isinstance(code, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", code):
                code = "API_HTTP_ERROR"
            raise ArnproxyError(code, status, request_id, retry, write and status >= 500)
        if "data" not in result:
            raise ArnproxyError("INVALID_API_RESPONSE", status, request_id, uncertain=write)
        return result

    def _send(self, method, path, headers, body):
        # HTTPSConnection does not follow redirects or use environment proxies.
        conn = http.client.HTTPSConnection("www.arnproxy.com", 443, timeout=self.timeout, context=ssl.create_default_context())
        try:
            conn.request(method, path, body=body, headers=headers)
            response = conn.getresponse()
            data = bytearray()
            deadline = time.monotonic() + self.timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ArnproxyError("TRANSPORT_TIMEOUT")
                if conn.sock is not None:
                    conn.sock.settimeout(remaining)
                part = response.read1(min(65536, _MAX + 1 - len(data)))
                if not part:
                    break
                data.extend(part)
                if len(data) > _MAX:
                    raise ArnproxyError("RESPONSE_TOO_LARGE")
            return response.status, {"retry-after": response.getheader("Retry-After", "")}, bytes(data)
        finally:
            conn.close()


def verify_webhook(raw_body: bytes, headers: dict, signing_secret: str, *, now: int | None = None):
    """Authenticate raw bytes first. Deduplicate event IDs durably in your application."""
    try:
        if type(raw_body) is not bytes or len(raw_body) > 4096 or type(headers) is not dict:
            raise ValueError()
        values = {}
        for k, v in headers.items():
            if type(k) is str and k.lower() in ("webhook-id", "webhook-timestamp", "webhook-signature"):
                if k.lower() in values or type(v) is not str:
                    raise ValueError()
                values[k.lower()] = v
        event_id, timestamp, signature = (values[k] for k in ("webhook-id", "webhook-timestamp", "webhook-signature"))
        if not re.fullmatch(r"evt_[a-f0-9]{32}", event_id) or not re.fullmatch(r"[1-9][0-9]{0,11}", timestamp) or len(signature) > 1024:
            raise ValueError()
        current = int(time.time()) if now is None else now
        if type(current) is not int or abs(current - int(timestamp)) > 300:
            raise ValueError()
        if type(signing_secret) is not str or not re.fullmatch(r"whsec_[A-Za-z0-9+/]{43}=", signing_secret):
            raise ValueError()
        secret = base64.b64decode(signing_secret[6:], validate=True)
        if len(secret) != 32 or base64.b64encode(secret).decode("ascii") != signing_secret[6:]:
            raise ValueError()
        expected = hmac.new(secret, (event_id + "." + timestamp + ".").encode("ascii") + raw_body, hashlib.sha256).digest()
        valid = False
        for item in signature.split():
            if not re.fullmatch(r"v1,[A-Za-z0-9+/]{43}=", item):
                continue
            actual = base64.b64decode(item[3:], validate=True)
            valid = hmac.compare_digest(expected, actual) or valid
        if not valid:
            raise ValueError()
        event = json.loads(raw_body.decode("utf-8"))
        if type(event) is not dict or event.get("id") != event_id or event.get("api_version") != "1" or type(event.get("data")) is not dict or not isinstance(event.get("type"), str):
            raise ValueError()
        return event
    except Exception:
        raise ArnproxyError("WEBHOOK_VERIFICATION_FAILED") from None
