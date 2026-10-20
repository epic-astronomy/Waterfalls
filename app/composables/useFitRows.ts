// Table rows that share the height left in the window, so a page of rows and
// the pager below it fit without scrolling; never below a compact row height.
// Bind tableBox around the table, footerBox to the pager's row, and the
// returned rowPx as the rows' height (--row-h).
export function useFitRows(rowsPerPage: Ref<number>, minPx = 37, maxPx = 80) {
  const tableBox = ref<HTMLElement>()
  const footerBox = ref<HTMLElement>()
  const rowPx = ref(minPx)
  function fitRows() {
    const el = tableBox.value
    if (!el || !el.offsetParent) return
    const body = el.querySelector('tbody')
    if (!body) return
    const scroller = el.closest('.overflow-y-auto')
    const viewBottom = scroller ? scroller.getBoundingClientRect().bottom : window.innerHeight
    const footer = (footerBox.value?.offsetHeight ?? 40) + 32 // the card footer and its padding
    const space = viewBottom - body.getBoundingClientRect().top - footer - 24 + (scroller?.scrollTop ?? 0)
    rowPx.value = Math.max(minPx, Math.min(maxPx, Math.floor(space / rowsPerPage.value)))
  }
  const observer = import.meta.client ? new ResizeObserver(() => fitRows()) : null
  watch(tableBox, (el, old) => { if (old) observer?.unobserve(old); if (el) observer?.observe(el) })
  watch(rowsPerPage, () => nextTick(fitRows))
  onMounted(() => window.addEventListener('resize', fitRows))
  onBeforeUnmount(() => { window.removeEventListener('resize', fitRows); observer?.disconnect() })
  return { tableBox, footerBox, rowPx, fitRows }
}
