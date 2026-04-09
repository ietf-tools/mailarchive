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
- R2 ml-templates
- R2 ml-messages-json

## Development

### Setup

Make sure you have Node.js 20.x or later installed first. Then clone the repository locally and run `npm install`.

### Dev Mode

Use the command `npm run dev` to start the dev server.

Use a command like this to upload file to local R2 
npx wrangler r2 object put ml-messages-json/dnsop/PxDc-GHOEmUhxElwrT49dqcRyag --file=test-data.json --local
npx wrangler r2 object put ml-templates/message-detail.html --file=sample-template.html --local

### Deployment

Use the command `npm run deploy` to deploy the project to Cloudflare Workers.