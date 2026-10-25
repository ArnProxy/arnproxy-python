# Public synthetic test data

The offline tests contain intentionally public examples, never keys copied
from ARNPROXY, Stripe or any other live service.

Webhook test keys are constructed **only inside tests** from exactly 32 ASCII
`X` or `Y` bytes. `secret_fixture` explicitly identifies that public recipe.
The test loaders combine the webhook format prefix with the Base64 encoding
of those bytes at runtime. Existing positive and negative signature vectors
are unchanged, so signature-verification coverage is retained.

Do not use these predictable values to configure any real account or webhook.
Actual API keys and signing secrets belong in server-side secret storage and
must never be committed, logged or put in a URL.

GitHub previously classified the fully spelled-out public test keys as
**Stripe Webhook Signing Secret** because the formats share a prefix. The
1.1.1 patch removes those complete literals from the current source without
disabling secret scanning or weakening runtime verification. Historical
test-value alerts may still require manual closure as **Used in tests**.
This explanation applies only to the documented synthetic X/Y values, not to
arbitrary secret-scanning alerts or real credentials.
