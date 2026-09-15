# Gupshup WhatsApp Integration Guide

This document covers everything you need to implement the `channel` module — the layer between our support system and WhatsApp via Gupshup.

Read the main design doc (`support-system-design.md`) first. This guide explains the Gupshup-specific mechanics that make that design work.

---

## What Gupshup is

Gupshup is a BSP (Business Service Provider) — a middleman between us and WhatsApp's Business API. We use their **Messaging API** product, not their bot-building platform. Our bot logic lives entirely in our `conversation` module. Gupshup is a dumb pipe: we send it messages, it delivers them to WhatsApp; users reply, Gupshup forwards those replies to our webhook.

If we ever switch providers (e.g. to Meta's Cloud API directly, or Twilio), only the `channel` module changes. Nothing else touches Gupshup.

---

## Prerequisites

You need three things:

1. **A Gupshup account** with a registered WhatsApp Business phone number
2. **An API key** — stored in Secret Manager, injected as an env var
3. **A callback URL** — your Cloud Run service's public URL, registered in Gupshup's dashboard as the webhook endpoint

No Meta template approvals needed to start. Templates only matter for one scenario (resolution messages sent after the 24-hour window — covered in §9 of this doc).

---

## The 24-hour session window

This is the single most important concept.

When a user sends you a message, WhatsApp opens a **24-hour window**. Inside that window, you can send them anything — text, interactive lists, buttons, images — for free, with no pre-approval. The window resets every time they message you.

Outside the window, you can only send **pre-approved template messages** (which cost money).

Our entire bot flow (language → product → name → centre → category → description → confirmation) happens inside the window, because the user initiated the conversation. The only time we hit the window boundary is when an admin takes more than 24 hours to resolve a ticket and needs to send the resolution.

---

## API basics

**Endpoint:**

```
POST https://api.gupshup.io/wa/api/v1/msg
```

**Content-Type:** `application/x-www-form-urlencoded`

**Authentication:** `apikey` header with your API key.

**Request body parameters (form-encoded):**

| Parameter     | Value                                    |
|---------------|------------------------------------------|
| `channel`     | `whatsapp`                               |
| `source`      | Your registered business phone number    |
| `destination` | The user's phone number (E.164, no `+`)  |
| `src.name`    | Your Gupshup app name                    |
| `message`     | JSON string — the message object         |

**Response on success:**

```json
{
  "status": "submitted",
  "messageId": "ee4a68a0-1203-4c85-8dc3-49d0b3226a35"
}
```

Store that `messageId`. It's how you track delivery receipts later.

Every outbound message uses this same endpoint. What changes is the `message` JSON.

---

## Sending messages

### Text messages

Used for: bot prompts ("Please share your name"), ticket confirmations, resolution messages inside the 24h window.

```json
{
  "type": "text",
  "text": "कृपया अपना नाम बताएं"
}
```

### Interactive list messages

Used for: language picker, product picker, category picker, disambiguation list (design doc §6 rule 4).

```json
{
  "type": "list",
  "title": "Select your product",
  "body": "Which product is this about?",
  "msgid": "product-picker",
  "globalButtons": [
    {
      "type": "text",
      "title": "Choose"
    }
  ],
  "items": [
    {
      "title": "Products",
      "subtitle": "",
      "options": [
        {
          "type": "text",
          "title": "Anganwadi VR",
          "description": "VR training for Anganwadi workers",
          "postbackText": "anganwadi-vr"
        },
        {
          "type": "text",
          "title": "German AI",
          "description": "German language learning",
          "postbackText": "german-ai"
        },
        {
          "type": "text",
          "title": "Poshan AI",
          "description": "Nutrition tracking",
          "postbackText": "poshan-ai"
        }
      ]
    }
  ]
}
```

**Limits:**

| Constraint              | Limit |
|-------------------------|-------|
| Sections in `items`     | 1–10  |
| Options per section     | ≤ 10  |
| Global buttons          | 1     |
| Title length            | 24 chars |
| Description length      | 72 chars |
| Body length             | 1024 chars |
| Global button title     | 20 chars |

These limits align with the design doc's invariant: enabled services ≤ 10, enabled categories per service ≤ 10. The WhatsApp hard cap and our Firestore constraint are the same number for the same reason.

**The `msgid` field** ties the user's reply back to this message. When the user taps an option, the inbound webhook includes this ID so you know which list they were responding to. Use it for context — e.g., `"product-picker"`, `"category-picker"`, `"disambiguate"`.

**The `postbackText` field** is the machine-readable value you get back when the user picks that option. Use your `serviceId` or `categoryId` here — not the display label. The user sees `"Anganwadi VR"`, your code gets `"anganwadi-vr"`.

### Quick-reply button messages

Used for: "About your [product] issue?" / "New problem" (design doc §6 rule 5), the Done button on the description step (§7).

```json
{
  "type": "quick_reply",
  "msgid": "reopen-or-new",
  "content": {
    "type": "text",
    "header": "Follow-up?",
    "text": "Is this about your recent Anganwadi VR issue (TKT-20260907-0042)?",
    "caption": ""
  },
  "options": [
    {
      "type": "text",
      "title": "Yes, same issue"
    },
    {
      "type": "text",
      "title": "New problem"
    }
  ]
}
```

**Limits:**

| Constraint        | Limit    |
|-------------------|----------|
| Buttons           | Max 3    |
| Button title      | 20 chars |
| Header            | 20 chars |
| Body              | 1024 chars |
| Footer (caption)  | 60 chars |

The `content` block can also be `image`, `video`, or `file` instead of `text` — we don't need that for this system.

### Template messages

Used for: resolution messages when the 24h window has expired (design doc §4.3 step 3).

```json
{
  "type": "template",
  "template": {
    "name": "resolution_notification",
    "namespace": "your_namespace_here",
    "language": {
      "policy": "deterministic",
      "code": "hi"
    },
    "components": [
      {
        "type": "body",
        "parameters": [
          {
            "type": "text",
            "text": "TKT-20260907-0042"
          },
          {
            "type": "text",
            "text": "Your VR headset calibration issue has been fixed..."
          }
        ]
      }
    ]
  }
}
```

Templates must be registered with Meta and approved before use. You submit them through the Gupshup dashboard. Each language variant needs separate approval.

At launch, you need at most **2 templates** (English + Hindi). The design doc's fallback: if a template isn't approved for the user's language, fall back to the English template.

---

## Receiving messages (inbound webhook)

Gupshup POSTs to your callback URL. You must return **HTTP 2xx within 10 seconds** or Gupshup will retry. Process asynchronously, acknowledge immediately.

### Envelope format

Every inbound message has this wrapper:

```json
{
  "app": "YourAppName",
  "timestamp": 1580546677791,
  "version": 2,
  "type": "message",
  "payload": {
    "id": "ABGGFlA5FpaVSEEE",
    "source": "919876543210",
    "type": "text",
    "payload": { ... },
    "sender": {
      "phone": "919876543210",
      "name": "Priya",
      "country_code": "91",
      "dial_code": "91"
    }
  }
}
```

Key fields:

- **`payload.id`** — WhatsApp message ID. This is your **dedupe key**. Write it to `inbound/{providerMessageId}` — if the doc already exists, return 200 and stop.
- **`payload.source`** — Phone number in E.164 without the `+`. This is the `waNumber` in your Firestore contact doc.
- **`payload.type`** — Determines what the user sent. See below.
- **`payload.sender.name`** — WhatsApp profile name. Not the same as `displayName` in your system (which you ask for explicitly).

### Message types you'll handle

**Text** — free-text answers (name, centre, description):

```json
{
  "type": "text",
  "payload": {
    "text": "My VR headset won't turn on"
  }
}
```

**List reply** — user tapped an option in your interactive list:

```json
{
  "type": "list_reply",
  "payload": {
    "title": "Anganwadi VR",
    "id": "product-picker",
    "reply": "Anganwadi VR",
    "postbackText": "anganwadi-vr",
    "description": "VR training for Anganwadi workers"
  }
}
```

The `postbackText` is the value you set when sending the list. The `id` matches the `msgid` you sent. Use `postbackText` for routing, not `title` (titles are display strings that might change).

**Button reply** — user tapped a quick-reply button:

```json
{
  "type": "button_reply",
  "payload": {
    "title": "Yes, same issue",
    "id": "reopen-or-new",
    "reply": "Yes, same issue"
  }
}
```

**Image** — user sent a photo:

```json
{
  "type": "image",
  "payload": {
    "url": "https://media.smsgupshup.com/...",
    "mediaId": "76534618xxxx",
    "caption": "See this crack on the headset"
  }
}
```

**Video** — same structure as image:

```json
{
  "type": "video",
  "payload": {
    "url": "https://media.smsgupshup.com/...",
    "mediaId": "89012345xxxx",
    "caption": ""
  }
}
```

**Document** — PDFs, etc. (unlikely in our case but handle it):

```json
{
  "type": "file",
  "payload": {
    "url": "https://media.smsgupshup.com/...",
    "mediaId": "12345678xxxx",
    "filename": "error_log.pdf"
  }
}
```

### Reply context (optional)

When a user long-presses one of your messages and replies to it specifically, you get an extra `context` object:

```json
{
  "payload": {
    "id": "ABGGFlA5FpaVSEEE",
    "source": "919876543210",
    "type": "text",
    "payload": { "text": "Still not working" },
    "context": {
      "id": "wamid.HBgNOTE4NjY...",
      "gsId": "ee4a68a0-1203-..."
    }
  }
}
```

`context.id` is the WhatsApp message ID of the message they replied to. This is how **routing rule 1** works (design doc §6): if that message's `ticketId` maps to a known ticket, route to it. If that ticket is closed and inside 7 days, offer to reopen.

---

## Delivery receipts (status webhook)

Gupshup sends these to the **same callback URL** but with `type: "message-event"` instead of `type: "message"`. You can distinguish them in your webhook handler by checking the top-level `type` field.

### Envelope format

```json
{
  "app": "YourAppName",
  "timestamp": 1580546677791,
  "version": 2,
  "type": "message-event",
  "payload": {
    "id": "gBEGkYaYVSEEAgnZxQ3JmKK6Wvg",
    "gsId": "ee4a68a0-1203-4c85-8dc3-49d0b3226a35",
    "type": "delivered",
    "destination": "919876543210",
    "payload": {
      "ts": 1585344476
    }
  }
}
```

### Status progression

```
enqueued → sent → delivered → read
                ↘ failed
```

| Status      | Meaning                                          | Action in our system                |
|-------------|--------------------------------------------------|-------------------------------------|
| `enqueued`  | Message reached WhatsApp's servers               | Update `providerStatus` to `queued` |
| `sent`      | Delivered to WhatsApp infrastructure              | Update `providerStatus` to `sent`   |
| `delivered` | Reached the user's phone                         | Update `providerStatus`. **If this is a resolution message → move ticket from `resolved` to `closed`** |
| `read`      | User opened the message                          | Update `providerStatus` to `read`. No ticket action — `delivered` already closed it |
| `failed`    | Send failed                                      | Update `providerStatus` to `failed`. Log the error code. Ticket stays `resolved` with `deliveryState: failed` — shows in needs-retry |

### Matching receipts to messages

The `gsId` in the receipt payload is the `messageId` you got back when you sent the message. Use it to find the corresponding message doc and its `ticketId`.

**Important:** `gsId` is only available for ~1 week after sending. And receipts may arrive **out of order**. Use the `payload.ts` field (seconds, from Meta) for the actual event time, not the outer `timestamp` (milliseconds, from Gupshup).

### Failed message payload

```json
{
  "payload": {
    "id": "9163a016-710e-41ee-978b-79a1adbd734e",
    "gsId": "72f61f22-5aa4-...",
    "type": "failed",
    "destination": "918x98xx21x4",
    "payload": {
      "code": 470,
      "reason": "Message failed to send because more than 24 hours have passed since the customer last replied to this number"
    }
  }
}
```

Common failure codes:

| Code | Meaning                                    |
|------|--------------------------------------------|
| 470  | 24h window expired                         |
| 1008 | User not opted in / inactive               |
| 1009 | Invalid phone number                       |
| 471  | Rate limit / spam filter                   |

When code 470 happens on a resolution message: the ticket stays `resolved`, `deliveryState: failed`. The hourly sweep retries once. If the admin sent freeform but the window closed between sending and delivery, you'll need the template fallback.

---

## Media handling

### Inbound media

When a user sends a photo or video, the webhook gives you a `url` and `mediaId`. **The URL expires** — possibly within minutes.

**Do not fetch media in the webhook request.** Write a message doc with `attachment.state: "pending"` and store the `mediaId`. Return 200. The 2-minute cron handles the rest.

### Fetching media (cron job)

The cron calls the Gupshup media download API:

```
GET https://api.gupshup.io/wa/api/v1/msg/{appId}/media/{mediaId}
```

With header: `apikey: {your_api_key}`

This returns the raw binary file. Write it to Cloud Storage, then update the message doc: `attachment.state: "stored"`, set `attachment.storagePath`.

**Rate limit:** Gupshup limits media downloads to **5 requests per hour** on some plans. The 2-minute cron with batching should stay well within this, but track attempts and back off. The design doc allows 5 attempts before marking `failed`.

**Alternative:** You can also download from the `url` in the original webhook payload, if you get to it before it expires. This doesn't count against the media download rate limit. The cron could try the URL first, fall back to the mediaId endpoint.

### Serving media to the dashboard

The dashboard never sees Gupshup URLs or Cloud Storage paths directly. The admin API mints **signed Cloud Storage URLs** (15-minute expiry) via `GET /attachments/:messageId/url`. The frontend requests a fresh URL each time.

---

## Webhook security

**Gupshup does not sign webhooks.** There is no HMAC signature or shared secret to verify on inbound payloads.

Options for securing the webhook:

1. **IP whitelisting** — Gupshup publishes a set of IPs their webhooks come from. Contact devsupport@gupshup.io for the list. You can configure this at the Cloud Run ingress level.
2. **Secret in the URL** — Register your webhook as `https://your-service.run.app/webhook/gupshup?secret=YOUR_SECRET` and check the query param. Simple, effective, the secret lives in Secret Manager.
3. **Both** — Belt and suspenders.

The design doc mentions "signature check" as a `channel` module responsibility. Since Gupshup doesn't offer one, implement option 2 at minimum.

---

## Putting it together: the full lifecycle

Here's what happens for a typical ticket, end to end, with the actual API calls:

```
USER sends "Hi"
  ← Gupshup POSTs to /webhook/gupshup
     type: "message", payload.type: "text"

  Check inbound/{id} → new message → proceed
  Find or create contact for 919876543210
  No session, no open tickets, no recent closed → start report flow
  Set session: { flow: "report", step: "language" }

  → POST api.gupshup.io/wa/api/v1/msg
     message: { type: "list", ... language options ... }

USER taps "Hindi"
  ← Gupshup POSTs to /webhook/gupshup
     type: "message", payload.type: "list_reply", postbackText: "hi"

  Session step is "language" → store language, advance to "service"

  → POST api.gupshup.io/wa/api/v1/msg
     message: { type: "list", ... product options ... }

USER taps "Anganwadi VR"
  ← Gupshup POSTs webhook
     postbackText: "anganwadi-vr"

  Session step is "service" → store serviceId
  Contact already has displayName and centreName → skip name + centre
  Advance to "category"

  → POST .../msg
     message: { type: "list", ... category options for anganwadi-vr ... }

USER taps "Hardware issue"
  ← Gupshup POSTs webhook
     postbackText: "hardware"

  Session step is "category" → store categoryId, advance to "description"

  → POST .../msg
     message: { type: "quick_reply", content: "Describe the issue...", options: [Done] }

USER sends "VR headset screen is cracked"
  ← webhook, type: "text"
  Append to session draft. Don't create ticket yet.

USER sends a photo
  ← webhook, type: "image", mediaId: "7653..."
  Write message doc with attachment.state: "pending"
  Append to session draft.

USER taps "Done"
  ← webhook, type: "button_reply", title: "Done"

  One transaction:
    - Allocate TKT-20260909-0001
    - Write ticket doc
    - Write "created" event
    - Stamp ticketId on all draft messages
    - Update contact.openTicketIds
    - Clear session

  → POST .../msg
     message: { type: "text", text: "Ticket TKT-20260909-0001 created..." }

~2 MINUTES LATER: media cron runs
  Find messages with attachment.state: "pending"
  GET api.gupshup.io/.../media/7653...
  Write bytes to Cloud Storage
  Update attachment.state → "stored"

ADMIN resolves (3 hours later, inside 24h window)
  POST /tickets/TKT-20260909-0001/resolution { text: "..." }

  → POST .../msg
     message: { type: "text", text: "Your issue has been resolved: ..." }
     (freeform — inside window)

  Gupshup sends receipt:
  ← webhook, type: "message-event", payload.type: "delivered"

  Ticket moves: resolved → closed. Done.
```

---

## What if the admin is slow? (post-24h scenario)

Same as above, except at the resolution step:

```
ADMIN resolves (28 hours later, outside 24h window)
  POST /tickets/TKT-20260909-0001/resolution { text: "..." }

  Check contact.lastInboundAt → 28 hours ago → outside window
  Cannot send freeform → use template

  → POST .../msg
     message: { type: "template", template: { name: "resolution_notification", language: { code: "hi" }, ... } }

  If template fails (not approved for Hindi) → retry with English template
  If English template also fails → ticket stays resolved, deliveryState: failed
     Shows in needs-retry queue on dashboard
     Hourly sweep retries once
```

---

## Error handling summary

| Scenario                             | What to do                                              |
|--------------------------------------|---------------------------------------------------------|
| Webhook returns non-2xx             | Gupshup retries. Your dedupe (inbound doc) prevents double-processing |
| Send API returns error               | Don't retry immediately. Log it. Let the sweep handle it |
| Media download fails                 | Leave `pending`. The 2-min cron retries. Give up at 5 attempts → `failed` |
| Delivery receipt says `failed`       | Ticket stays `resolved`. Flag `deliveryState: failed`. Sweep retries once |
| 24h window expired (code 470)        | Switch to template. If no template approved → surface on dashboard |
| Rate limited (429)                   | Back off. The cron will pick it up next cycle            |

---

## Testing

Use Gupshup's **sandbox** for development. It gives you a test phone number and a test API key so you can send/receive without a production WhatsApp number.

The Firebase Emulator Suite handles Firestore and Auth locally. Set `FIRESTORE_EMULATOR_HOST` and the SDK redirects itself — no test/prod branching needed.

For automated tests: mock the Gupshup HTTP calls with `httpx`'s transport mocking. The `channel` module should expose functions like `send_text(destination, text)`, `send_list(destination, list_config)`, etc. — thin wrappers around the API call. Test the `conversation` and `tickets` modules against the emulator with the channel mocked.

---

## Quick reference

| What                        | Value / URL                                                    |
|-----------------------------|----------------------------------------------------------------|
| Send message endpoint       | `POST https://api.gupshup.io/wa/api/v1/msg`                   |
| Media download endpoint     | `GET https://api.gupshup.io/wa/api/v1/msg/{appId}/media/{mediaId}` |
| Auth                        | `apikey` header                                                |
| Content type (send)         | `application/x-www-form-urlencoded`                            |
| Webhook payload type field  | `"message"` (inbound) or `"message-event"` (receipt)           |
| Dedupe key                  | `payload.id` (WhatsApp message ID)                             |
| Receipt match key           | `gsId` (= `messageId` from send response)                     |
| Max list options            | 10 per section, 10 sections                                   |
| Max buttons                 | 3                                                              |
| Session window              | 24h from last user message                                     |
| Media download rate limit   | 5/hour (plan-dependent)                                        |
| Webhook timeout             | 10 seconds                                                     |

**Official docs:**

- Gupshup developer guide: https://www.gupshup.io/developer/guide?name=whatsapp-api-documentation
- Send API reference: https://docs.gupshup.io/reference/msg
- Inbound message types: https://docs.gupshup.io/docs/message-type-inbound
- Message events (delivery receipts): https://docs.gupshup.io/docs/message-events
- Interactive messages: https://docs.gupshup.io/docs/interactive-messages
- Media download: https://partner-docs.gupshup.io/reference/downloadmedia
- Webhook setup: https://docs.gupshup.io/docs/what-is-a-webhook
