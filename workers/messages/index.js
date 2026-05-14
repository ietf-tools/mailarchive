import Mustache from 'mustache'
import template from './templates/message-detail.html'

// Match Django's html.escape: encode only &, <, >, ", ' — not / or =
Mustache.escape = (text) => String(text)
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&#x27;')

/**
 * Main worker entry point
 */
export default {
  async fetch (request, env, ctx) {
    try {
      const url = new URL(request.url)

      // Only handle /arch/msg/ and /arch/ajax/msg/ paths
      const { pathname } = url
      if (!pathname.startsWith('/arch/msg/') && !pathname.startsWith('/arch/ajax/msg/')) {
        return proxyToOrigin(request, env)
      }

      // Check for authentication - if present, always proxy
      if (isAuthenticated(request)) {
        return proxyToOrigin(request, env, 'authenticated')
      }

      // Parse URL to extract list, hashcode, and request type
      const parsed = parseMessageUrl(pathname)
      if (!parsed) {
        return proxyToOrigin(request, env, 'invalid-url')
      }

      const { list, hashcode, isAjax } = parsed

      // Try to serve from R2
      try {
        const r2Key = `${list}/${hashcode}`
        const messageJson = await env.MESSAGES.get(r2Key)

        if (!messageJson) {
          return proxyToOrigin(request, env, 'r2-miss')
        }

        const data = JSON.parse(await messageJson.text())

        if (isAjax) {
          return new Response(renderAjaxFragment(data), {
            status: 200,
            headers: {
              'Content-Type': 'text/html; charset=utf-8',
              'Cache-Control': 'public, max-age=86400',
              'X-Served-By': 'cloudflare-worker-r2',
            },
          })
        }

        const html = renderTemplate(template, data, list)
        return new Response(html, {
          status: 200,
          headers: {
            'Content-Type': 'text/html; charset=utf-8',
            'Cache-Control': 'public, max-age=3600',
            'X-Served-By': 'cloudflare-worker-r2',
          },
        })
      } catch (error) {
        console.error('Error serving from R2:', error.message)
        return proxyToOrigin(request, env, 'r2-error')
      }
    } catch (error) {
      console.error('Worker error:', error.message)
      return proxyToOrigin(request, env, 'worker-error')
    }
  },
}

/**
 * Check if request is authenticated
 */
function isAuthenticated (request) {
  const cookies = request.headers.get('Cookie') || ''
  return /(?:^|;\s*)sessionid=/.test(cookies)
}

/**
 * Parse message URL to extract list name, hashcode, and whether it's an ajax request
 * Handles /arch/msg/{list}/{hashcode}/ and /arch/ajax/msg/{list}/{hashcode}/
 * Returns { list, hashcode, isAjax } or null if invalid
 */
function parseMessageUrl (pathname) {
  const match = pathname.match(/^\/arch\/(ajax\/)?msg\/([^/]+)\/([^/]+)\/?$/)

  if (!match) {
    return null
  }

  const isAjax = !!match[1]
  const list = match[2]
  const hashcode = match[3]

  // Base64.urlsafe charset: A-Z, a-z, 0-9, -, _
  if (!/^[A-Za-z0-9_-]{27}$/.test(hashcode)) {
    return null
  }

  return { list, hashcode, isAjax }
}

/**
 * Render template with message data
 */
function renderTemplate (template, data, listName) {
  // Prepare context for template
  const context = {
    ...data,
    // Add computed fields
    list_name: listName,
    formatted_date: formatDate(data.date),
    formatted_updated: formatDate(data.updated),
    detail_url: `/arch/msg/${listName}/${data.hashcode.replace(/=+$/, '')}`,
    download_url: `/arch/msg/${listName}/${data.hashcode.replace(/=+$/, '')}/download`,
    // Parse from email
    from_name: parseEmailName(data.frm),
    from_email: parseEmailAddress(data.frm),
    // Threading helpers
    has_thread: data.thread_depth > 0,
    is_reply: data.in_reply_to !== null,
  }

  return Mustache.render(template, context)
}

/**
 * Render minimal HTML fragment for the search view pane ajax request.
 * Mirrors Django's message_ajax.html: body HTML + thread snippet.
 */
function renderAjaxFragment (data) {
  return `${data.body || ''}\n\n<div id="message-thread">\n    ${data.thread_snippet || ''}\n</div>`
}

/**
 * Format ISO date string to human-readable format
 */
function formatDate (isoString) {
  if (!isoString) return ''

  try {
    const date = new Date(isoString)
    return date.toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      timeZoneName: 'short',
    })
  } catch (error) {
    return isoString
  }
}

/**
 * Parse email name from "Name <email>" format
 */
function parseEmailName (fromField) {
  if (!fromField) return ''

  const match = fromField.match(/^(.+?)\s*<.+>$/)
  if (match) {
    return match[1].replace(/^["']|["']$/g, '').trim()
  }

  // If no name, return local part of email
  const emailMatch = fromField.match(/([^@]+)@/)
  return emailMatch ? emailMatch[1] : fromField
}

/**
 * Parse email address from "Name <email>" or plain email format
 */
function parseEmailAddress (fromField) {
  if (!fromField) return ''

  const match = fromField.match(/<(.+?)>/)
  if (match) {
    return match[1]
  }

  return fromField
}

/**
 * Proxy request to origin server
 */
async function proxyToOrigin (request, env, reason = 'default') {
  const originUrl = env.ORIGIN_URL || 'https://mailarchive.ietf.org'
  const url = new URL(request.url)

  // Build origin URL
  const targetUrl = new URL(url.pathname + url.search, originUrl)

  // Create new request with preserved headers
  const newRequest = new Request(targetUrl, {
    method: request.method,
    headers: request.headers,
  })

  try {
    const response = await fetch(newRequest)

    // Clone response and add custom header
    const newResponse = new Response(response.body, response)
    newResponse.headers.set('X-Worker-Action', `proxy-to-origin:${reason}`)

    return newResponse
  } catch (error) {
    console.error('Error proxying to origin:', error.message)

    // Return error response
    return new Response('Service Unavailable', {
      status: 503,
      headers: {
        'Content-Type': 'text/plain',
        'X-Worker-Action': `proxy-error:${reason}`,
      },
    })
  }
}
