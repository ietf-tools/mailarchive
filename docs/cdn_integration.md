### CDN Integration *(Cloudflare)*

As of `v1.12.4`, mail archive supports a "Static Mode" which resembles the MHonArc interface.
When enabled, from the Settings menu, the user is directed to `/arch/browse/static/` pages.
Cloudflare has been configured to cache these pages for `CACHE_CONTROL_MAX_AGE`.