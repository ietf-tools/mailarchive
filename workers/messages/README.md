<div align="center">

<img src="logo.png" alt="Cloudflare Workers" height="125" />

#### Cloudflare Worker Proxy for serving message files

</div>

## Summary

This Cloudflare Worker processes requests for archive message details. It does the following:

- if the request is unauthenticated:
  - if message object exists in blob storage (name from URL: dnsop/rY-OYgyL59afmpApNrW3UPo5wuM)
    - get json blob from storage
    - use json as context for template and return HTML
- else fetch response from source and return

## Routes
- /arch/msg/*
- /arch/ajax/msg/* (future)

## Bindings
- R2 ml-messages-json
- R2 ml-templates (reserved for runtime template loading; not read today, the template is
  bundled from `templates/message-detail.html` at build time)

## Development

### Setup

Make sure you have Node.js 20.x or later installed first. Then clone the repository locally and run `npm install`.

### Dev Mode

Use the command `npm run dev` to start the dev server.

Use a command like this to upload file to local R2 
npx wrangler r2 object put ml-messages-json/dnsop/PxDc-GHOEmUhxElwrT49dqcRyag --file=test-data.json --local

The template is not loaded from R2; edit `templates/message-detail.html` (or regenerate it
with `create_cf_worker_templates()` on the Django side) and restart the dev server.

### Deployment

Use the command `npm run deploy` to deploy the project to Cloudflare Workers.