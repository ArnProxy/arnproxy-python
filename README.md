# ARNPROXY SDK for Python

Version **1.1.1** · MIT · Python 3.10+.

Source client for https://www.arnproxy.com/account/api/v1/ . Covers all **77 documented resources** through a generic request method, plus account/capabilities convenience methods and webhook HMAC verification. This client is for ARNPROXY, not a direct connection to an upstream provider.

## Installation

Install from this source folder with `python -m pip install .`. This is not a claim of publication on PyPI.

Keep the included resources.json at its shipped location. Set your own existing API key in the **server-side** ARNPROXY_API_KEY environment variable; never put it in source code, a URL or a browser app. Downloading or installing this library does **not** grant API access. Access is still controlled on the server; the current rollout remains test-account-only.

## Read-only first request

```python
from arnproxy import Client
import os
client = Client(os.environ['ARNPROXY_API_KEY'])
print(client.account()['data']['id'])
```

## Operations and safety

Write and provider-read guards are OFF by default. Enabling a local guard never bypasses server account, ownership, verification, scope, IP or rate-limit checks. Consent/price/revision fields are not automatically filled.

For idempotent resources, create and durably retain a unique operation key (16–100 ASCII letters/digits/underscore/hyphen). It is not your API key. Pass that SAME key to the documented status resource after an uncertain result. Do not create another operation, retry a paid order, or infer success from HTTP 200 with state=unknown/review. The SDK does not automatically poll or repeat an operation.

Errors expose only a code, HTTP status, request ID, retry-after and uncertainty flag, never raw response data. Do not log responses containing proxy passwords. Request and response size limit: 2 MiB. Default timeout: 20 seconds, configurable from 1–60. TLS verification is on; redirects and environment proxies are not used. Runtime DNS/connection behavior does not promise a strict universal deadline.

See the [API reference](https://www.arnproxy.com/account/api/docs/) and [complete usage notes](USAGE.md).

## Optional webhooks

Use the verification helper with original raw body bytes and webhook-id, webhook-timestamp, webhook-signature headers, plus the separate whsec_ secret. API keys are not webhook secrets. A signature proves authenticity, not business completion. Deduplicate event IDs in durable storage; events may be delayed or out of order. Webhooks are optional.

## Security

Never commit a real API key, customer data or production configuration. Report security problems privately to ARNPROXY support through https://www.arnproxy.com/ rather than putting secrets in an issue.

## License

MIT, copyright 2026 ARNPROXY. The license covers this SDK only, not the hosted proxy service or its server implementation.

## Offline tests

`python tests/run.py . tests/fixtures.json`

Uses synthetic fixtures and mocked transports only. No real API key or hosted API call is required. GitHub Actions runs this check on pushes and pull requests.

Public synthetic test-key recipes are documented in [TESTING.md](TESTING.md). Never use them with a live service.
