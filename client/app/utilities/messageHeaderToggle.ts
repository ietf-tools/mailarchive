// Inserts a "Show header"/"Hide header" toggle after #msg-date that shows or
// hides the full #msg-header block (hidden by default via CSS), mirroring the
// behaviour of detail.js / mailarch.js loadMessage(). Operates on the rendered
// message-body HTML (injected via v-html), so it runs client-side after render.
export function addHeaderToggle(root: HTMLElement | null) {
  if (!root) return
  const dateEl = root.querySelector('#msg-date')
  if (!dateEl || root.querySelector('#toggle-msg-header')) return

  const link = document.createElement('a')
  link.id = 'toggle-msg-header'
  link.className = 'toggle'
  link.href = '#'
  link.textContent = 'Show header'
  link.addEventListener('click', (event) => {
    event.preventDefault()
    const header = root.querySelector<HTMLElement>('#msg-header')
    if (header) header.style.display = header.style.display === 'block' ? 'none' : 'block'
    link.textContent = link.textContent === 'Show header' ? 'Hide header' : 'Show header'
  })
  dateEl.insertAdjacentElement('afterend', link)
}
