# Email Message Worker

A lightweight Cloudflare Worker that serves email message detail pages from R2 storage with graceful fallback to the origin server.

## Features

- ✅ **R2-backed rendering**: Serves pre-rendered JSON from R2 with Mustache templates
- ✅ **Authentication-aware**: Automatically proxies authenticated requests to origin
- ✅ **Graceful fallback**: Falls back to origin on any error or missing content
- ✅ **Template caching**: In-memory template cache with configurable TTL
- ✅ **Hashcode validation**: Validates 27-character base64 hashcodes
- ✅ **Lightweight**: ~275 lines, single dependency (Mustache)

## Installation

```bash
cd workers/messages
npm install
```

## Development

The HTML template (`templates/message-detail.html`) is a generated artifact and
is not committed to git. Before running locally, generate it from the Django app:

```bash
# From the project root:
backend/manage.py create_cf_worker_templates \
  --settings=mlarchive.settings.settings_collectstatics
```

```bash
# Start local development server
npm run dev

# Test with curl
curl http://localhost:8787/arch/msg/dnsop/aBcDeFgHiJkLmNoPqRsTuVwXyZ1/
```

## Deployment

```bash
# Deploy to Cloudflare
npm run deploy
```

## Configuration

Edit `wrangler.toml` to configure:

- **R2 Bindings**: `MESSAGES` and `TEMPLATES` buckets
- **Origin URL**: Default `https://mailarchive.ietf.org`
- **Template name**: Default `message-detail.html`
- **Template cache TTL**: Default 3600 seconds

## How It Works

### Request Flow

1. **Authentication Check**: If `sessionid` cookie present → proxy to origin
2. **URL Parsing**: Extract list name and hashcode from `/arch/msg/{list}/{hashcode}/`
3. **R2 Lookup**: Try to fetch JSON from `ml-messages-json/{list}/{hashcode}`
4. **Template Rendering**: If found, render with Mustache template
5. **Fallback**: On any error or miss → proxy to origin

### R2 Buckets

- **ml-messages-json**: Message data as JSON
  - Key format: `{list}/{hashcode}` (e.g., `dnsop/aBcDeFgHiJkLmNoPqRsTuVwXyZ1`)
  - Content: JSON from `Message.as_json()` method

- **ml-templates**: HTML templates - reserved, not read by the worker today
  - The worker bundles `templates/message-detail.html` at build time; the file is
    generated from the Django template by `create_cf_worker_templates()`
  - Kept for a future worker that loads its template at runtime
  - Key: `message-detail.html`
  - Format: Mustache template with message data

### Template Context

All JSON fields are available, plus computed fields:

- `list_name`: Email list name from URL
- `formatted_date`: Human-readable date
- `formatted_updated`: Human-readable updated date
- `detail_url`: Message detail URL
- `download_url`: Message download URL
- `from_name`: Parsed sender name
- `from_email`: Parsed sender email
- `has_thread`: Boolean, true if message is threaded
- `is_reply`: Boolean, true if message is a reply

### Example Mustache Template

```html
<!DOCTYPE html>
<html>
<head>
  <title>{{subject}} - {{list_name}}</title>
</head>
<body>
  <h1>{{subject}}</h1>
  <div class="meta">
    <strong>From:</strong> {{from_name}} &lt;{{from_email}}&gt;<br>
    <strong>Date:</strong> {{formatted_date}}<br>
    {{#is_reply}}
      <strong>In-Reply-To:</strong> {{in_reply_to_value}}<br>
    {{/is_reply}}
  </div>
  <pre>{{content}}</pre>
</body>
</html>
```

## Testing

### Create Test Data

Upload test JSON to R2:

```bash
# Example JSON file
cat > test-message.json <<EOF
{
  "id": 12345,
  "msgid": "<test@example.com>",
  "hashcode": "aBcDeFgHiJkLmNoPqRsTuVwXyZ1",
  "subject": "Test Message",
  "frm": "Test User <test@example.com>",
  "date": "2026-02-18T10:30:00+00:00",
  "content": "This is a test message body.",
  "thread_depth": 0,
  "in_reply_to": null
}
EOF

# Upload to R2
wrangler r2 object put ml-messages-json/testlist/aBcDeFgHiJkLmNoPqRsTuVwXyZ1 --file test-message.json
```

### Test URLs

- Public message (R2): `https://localhost:8787/arch/msg/testlist/aBcDeFgHiJkLmNoPqRsTuVwXyZ1/`
- Authenticated (proxy): Add cookie `sessionid=test`
- Missing in R2 (proxy): Use non-existent hashcode
- Invalid URL (proxy): Wrong hashcode length

## Monitoring

The worker adds custom headers for debugging:

- **X-Served-By**: `cloudflare-worker-r2` when served from R2
- **X-Worker-Action**: Proxy reason when falling back to origin
  - `proxy-to-origin:authenticated` - Request was authenticated
  - `proxy-to-origin:invalid-url` - URL didn't match pattern
  - `proxy-to-origin:r2-miss` - JSON not found in R2
  - `proxy-to-origin:template-missing` - Template not in R2
  - `proxy-to-origin:r2-error` - Error reading R2 or rendering

## Performance

- **Template caching**: Fetched once per worker instance
- **R2 latency**: <50ms typical
- **Rendering**: <10ms with Mustache
- **Total TTFB**: <200ms for R2-served content

## Security

- **Authentication bypass prevention**: Always checks auth indicators first
- **Template escaping**: Mustache auto-escapes HTML by default
- **Read-only R2**: Worker only reads from R2, never writes
- **Origin preservation**: All headers preserved when proxying

## Troubleshooting

### Worker returns 503

- Check R2 bucket bindings in `wrangler.toml`
- Verify origin URL is accessible
- Check worker logs: `wrangler tail`

### Template not rendering

- The template is bundled at build time from `templates/message-detail.html`; regenerate
  it with `create_cf_worker_templates()` and redeploy. R2 `ml-templates` is not read
- Check template syntax (Mustache)
- Check browser console and worker logs

### Always proxies to origin

- Check R2 key format: `{list}/{hashcode}` (no leading slash)
- Verify JSON exists: `wrangler r2 object get ml-messages-json/{list}/{hashcode}`
- Check hashcode is exactly 27 characters, no padding

## Production Deployment

1. Configure R2 buckets in Cloudflare dashboard
2. Regenerate `templates/message-detail.html` with `create_cf_worker_templates()` if the
   Django template changed (it is bundled at build time; `ml-templates` is not read)
3. Update `wrangler.toml` with production config
4. Deploy: `npm run deploy`
5. Add route in Cloudflare dashboard or uncomment in `wrangler.toml`
6. Monitor logs and metrics

## License

Part of the IETF Mail Archive project.
