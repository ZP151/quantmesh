// Read-only browser DOM probe. Evaluate after opening a stored snapshot at375px
// and letting the existing150ms responsive button transitions settle.
// It checks rendered geometry rather than implementation classes or API mocks.
(() => {
  const main = document.querySelector('main')
  const input = main.querySelector('input[type="file"]')
  const importButton = [...main.querySelectorAll('button')].find(element =>
    /^(Import snapshot|导入快照)$/.test(element.textContent.trim()))
  const rect = element => {
    const bounds = element.getBoundingClientRect()
    return { x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height }
  }
  const inputRect = rect(input)
  const importRect = rect(importButton)
  const targets = [...main.querySelectorAll('button,summary,input[type="file"]')].map(element =>
    ({ name: element.textContent.trim() || element.id, ...rect(element) }))
  const failures = []
  if (!main.querySelector('#snapshot-qualification')) failures.push('Open a stored snapshot before running the probe.')
  if (innerWidth >= 640) failures.push('Probe requires the compact viewport.')
  if (inputRect.y + inputRect.height > importRect.y + 1) failures.push('File selector and import action share a row.')
  for (const target of targets) {
    if (target.height < 43.9) failures.push(`${target.name}: height ${target.height} <44px`)
  }
  if (document.documentElement.scrollWidth > innerWidth) failures.push('Horizontal document overflow.')
  return {
    status: failures.length ? 'FAIL' : 'PASS', failures,
    viewport: { width: innerWidth, height: innerHeight },
    documentWidth: document.documentElement.scrollWidth,
    input: inputRect, importAction: importRect, targets,
  }
})()
