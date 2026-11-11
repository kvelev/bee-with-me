// Builds the hover tooltip of a tracker marker out of DOM nodes. Every value (names, ranks, phone,
// group description, device name) is operator or device data, so it is only ever set with
// `textContent`: never markup, never innerHTML (B52, security F4).
import { photoImage, safePhotoUrl } from './photoMarker'
import { freshnessOf, LIVE } from './freshness'

function el(tag, { text, style } = {}) {
  const node = document.createElement(tag)
  if (text != null) node.textContent = text
  if (style) node.style.cssText = style
  return node
}
function add(parent, ...children) {
  for (const c of children) if (c) parent.append(c)
}
const br = () => document.createElement('br')

// The photo: same-origin only (the marker's rule, TP-01), set through properties, never markup.
// The tooltip re-renders on every pointermove, so it never starts a load of its own: it shows the
// photo only when the shared cache (`photoImage`, with its retry backoff) reports it loaded, and
// otherwise no image box at all (B56). The first hover warms the cache; nothing is logged (DP-02).
function photoNode(pos, name) {
  const src = safePhotoUrl(pos.photo_url)
  if (!src || !photoImage(src)) return null
  const img = document.createElement('img')
  img.className = 'tt-photo'
  const quiet = freshnessOf(pos) !== LIVE
  if (pos.sos_active) img.classList.add('tt-photo--sos')   // red ring: SOS only
  if (quiet) img.classList.add('tt-photo--stale')          // an SOS gone quiet is dimmed too (BP-01)
  img.alt = name
  img.width = 96
  img.height = 96
  img.decoding = 'async'
  // A dimmed filter would also dim a red ring on the image itself, so a quiet SOS keeps its
  // red ring on a wrapper and only the photo inside is dimmed.
  let node = img
  if (pos.sos_active && quiet) {
    node = el('span')
    node.className = 'tt-photo-ring'
    node.append(img)
  }
  img.onerror = () => node.remove()
  img.src = src
  return node
}

export function renderTrackerTooltip(target, pos, groupDetail, { showPhotos = true } = {}) {
  const nodes = []
  const sos = pos.sos_active ? el('span', { text: ' 🚨 SOS', style: 'color:#ef4444;font-weight:700' }) : null
  const bat = pos.battery_voltage != null ? [br(), document.createTextNode(`🔋 ${pos.battery_voltage.toFixed(1)} V`)] : []
  const time = pos.recorded_at ? [br(), document.createTextNode(`🕐 ${new Date(pos.recorded_at).toLocaleTimeString()}`)] : []
  const mgrs = el('span', { text: pos.mgrs ?? '', style: 'font-family:monospace;font-size:11px' })

  if (pos.displayLabel) {
    const members = groupDetail?.members ?? []
    nodes.push(el('strong', { text: pos.displayLabel }), sos)
    if (groupDetail?.description) {
      nodes.push(br(), el('span', { text: groupDetail.description, style: 'font-size:11px;color:#aaa;font-style:italic' }))
    }
    if (pos.full_name) {
      nodes.push(br(), el('span', {
        text: pos.rank ? `${pos.full_name} · ${pos.rank}` : pos.full_name, style: 'font-size:11px;color:#aaa',
      }))
    }
    nodes.push(br(), mgrs, ...bat, ...time)
    if (members.length) {
      nodes.push(br(), el('span', { text: 'Members', style: 'font-size:10px;color:#888;text-transform:uppercase;letter-spacing:.05em' }))
      for (const m of members) {
        nodes.push(br(), el('span', {
          text: `${m.is_leader ? '★ ' : '· '}${m.full_name}${m.rank ? ` (${m.rank})` : ''}`,
          style: `color:${m.is_leader ? '#ffc900' : '#ccc'}`,
        }))
      }
    }
  } else {
    const name = pos.full_name || pos.device_name || `SN:${pos.dev_sn}`
    nodes.push(el('strong', { text: name }), sos)
    if (pos.repeater_mode) nodes.push(el('span', { text: ' ↩ Repeater', style: 'color:#a78bfa' }))
    nodes.push(br(), mgrs)
    if (pos.altitude_m != null) nodes.push(br(), document.createTextNode(`⛰ ${pos.altitude_m} m`))
    nodes.push(...bat, ...time)
    if (pos.phone) nodes.push(br(), document.createTextNode(`📞 ${pos.phone}`))
  }
  const body = nodes.filter(Boolean)
  const name = pos.displayLabel ? (pos.full_name || pos.displayLabel) : (pos.full_name || pos.device_name || `SN:${pos.dev_sn}`)
  const photo = showPhotos ? photoNode(pos, name) : null
  if (!photo) {
    target.replaceChildren(...body)
    return
  }
  const text = el('div', { style: 'min-width:0' })
  text.append(...body)
  const row = el('div')
  row.className = 'tt-row'
  row.append(photo, text)
  target.replaceChildren(row)
}
