# Usage notes

ARNPROXY thin clients / SDK 1.1.0
PHP 8.1+ with cURL; Python 3.10+; Node.js 20+; Java 17+ with Gson via Maven; Go 1.22+.
PHP/Python/Node/Go do not need third-party runtime packages; Java needs Gson. Preserve the folders and adjacent resources.json.
request() covers all 77 documented resources, not all server-side permissions or capabilities.
Disabled resources remain disabled. Access is still restricted to test accounts 2 and 10231.
Downloading a client does not enable API access.

START — account read only, no purchase/provider operation
Set ARNPROXY_API_KEY locally in your server environment. Never commit it, expose it to a browser,
or distribute it with the SDK. Run examples from the extracted package root.

PHP:
require __DIR__.'/php/Arnproxy.php';
$client = new \ArnproxySdk\Client(getenv('ARNPROXY_API_KEY'));
$response = $client->account();
echo $response['data']['id'], PHP_EOL;

Python:
from python.arnproxy import Client
import os
client = Client(os.environ['ARNPROXY_API_KEY'])
print(client.account()['data']['id'])

Node.js, example.mjs:
import {Client} from './node/arnproxy.mjs';
const client = new Client(process.env.ARNPROXY_API_KEY);
console.log((await client.account()).data.id);

GENERIC REQUEST
PHP: $client->request('order_delivery', ['id'=>YOUR_OWN_ORDER_ID]);
Python: client.request('order_delivery', {'id': YOUR_OWN_ORDER_ID})
Node: await client.request('order_delivery', {id: YOUR_OWN_ORDER_ID})
Returns the full JSON envelope: ok, data, meta; request ID is meta.request_id.
Transport/HTTP/envelope failures throw ArnproxyError with no raw response or key attached.
PHP error code: error_code; Python/Node: code. Shared fields: http_status, request_id,
retry_after (seconds or null), uncertain (the result of a write might be unknown).
A successful HTTP envelope may contain state=unknown/review; it is not operation completion.
Never log client objects, credential responses, or traceback local variables.

GUARDS AND OPERATIONS
allow_writes=false and allow_provider_reads=false by default. Local POST reads such as quotes are allowed.
Set allow_provider_reads=true for provider reads/reconciliation, allow_writes=true for mutations.
These are client-side safety switches, not server permissions. Consent fields are never auto-filled.
Use the parameter/response guide for bodies, revisions, scopes and price confirmations.
PHP options: new Client($key,['allow_writes'=>true,'allow_provider_reads'=>true]);
Python: Client(key, allow_writes=True, allow_provider_reads=True)
Node: new Client(key,{allow_writes:true,allow_provider_reads:true})

For resources requiring Idempotency-Key, create and durably retain your own operation_key:
16–100 ASCII letters/digits/_/-. It is not your API key.
PHP: request('purchase', $body, $savedOperationKey)
Python: request('purchase', body, operation_key=saved_key)
Node: request('purchase', body, {operation_key:savedKey})
The client derives short paths/methods from resources.json; the API key is only in Authorization.
After an uncertain response, do not start a new operation. Query the related status resource
with the SAME operation_key. status_resource in resources.json identifies that resource.
GET values are scalar text/integer/boolean; use the documented comma-separated string for lists.
POST parameters are a JSON object. Use integer total_minor values for monetary confirmations.

BOUNDARIES
Destination is fixed to https://www.arnproxy.com/account/api/v1/ . No custom endpoint or key-in-URL mode.
TLS certificate verification on, redirects blocked, no environment proxy use.
No automatic retry, background task, bulk writing, pagination or polling.
timeout defaults to 20 seconds, range 1–60. Python bounds blocking socket operations;
it does not promise a strict aggregate deadline for DNS/header reads.
Request/response limit: 2 MiB. Paginate or use direct HTTP for larger data. Node numbers must be within
the JavaScript safe range. Wait for retry_after on HTTP 429; counters are not reset by the SDK.
This is a versioned downloadable source package, not an NPM/PyPI/Composer publication.
New resources require a client contract update.

OPTIONAL WEBHOOK AUTHENTICATION
PHP: Client::verifyWebhook($rawBytes,$headers,$whsecSecret)
Python: from python.arnproxy import verify_webhook
        verify_webhook(raw_bytes, headers, whsec_secret)
Node: import {verifyWebhook} from './node/arnproxy.mjs';
      verifyWebhook(rawBuffer, headers, whsecSecret)
The webhook signing secret is NOT the API key. Pass original bytes BEFORE re-encoding JSON,
and the webhook-id/webhook-timestamp/webhook-signature headers. Keep your server clock accurate.
HMAC-SHA256; 300-second tolerance; 4096-byte payload bound. Verification authenticates the envelope;
it does not prove business success, account authorization or first-time delivery.
Deduplicate event IDs in a durable application database; do not execute duplicate side effects.
Handle only event types your application recognizes. Persist to a reliable queue before returning 2xx.
Events are not ordered. api.request.result is HTTP telemetry, and an auto-renewal configuration event
is not a charge. Polling existing operation status endpoints remains available without webhooks.

Guide: https://www.arnproxy.com/account/api/docs/
No keys, customer/proxy values or automatically executed examples are included.


JAVA 17+
import com.arnproxy.sdk.Client;
var client = new Client(System.getenv("ARNPROXY_API_KEY"));
System.out.println(client.account().getAsJsonObject("data").get("id").getAsInt());
For writes: new Client(key, new Client.Options(true,true,20)).
Generic request: client.request("order_delivery", Map.of("id", ownOrderId), null).
Operation key is the third argument. Error: ApiException.code/httpStatus/requestId/retryAfter/uncertain.
Webhook: Client.verifyWebhook(rawBytes, headers, whsecSecret, Instant.now().getEpochSecond()).
Maven resolves Gson; the Java package is source, not an automatically installed JAR.

GO 1.22+
Import github.com/arnproxy/arnproxy-go after publication, or use the shipped local go module.
client, err := arnproxy.New(os.Getenv("ARNPROXY_API_KEY"))
if err != nil { return }
result, err := client.Account(context.Background())
if err != nil { return }
var account struct { ID int `json:"id"` }
if result.DecodeData(&account) != nil { return }
fmt.Println(account.ID)
For writes: arnproxy.New(key, arnproxy.Options{AllowWrites:true,AllowProviderReads:true,Timeout:20*time.Second}).
Generic request: client.Request(ctx,"order_delivery",map[string]any{"id":ownOrderID},"").
Operation key is the fourth argument. APIError: Code/HTTPStatus/RequestID/RetryAfterSeconds/Uncertain.
Webhook: arnproxy.VerifyWebhook(rawBytes, headers, whsecSecret, time.Now()).
Response.Data is json.RawMessage; Response.DecodeData decodes into your own type.
