<script setup lang="ts">
import type { PropType } from 'vue'

// A calendar for picking one day, in the time zone chosen on the page (or in
// UTC with `utc`). The title steps up from the days of a month to the months
// of a year and then to the years, for looking back quickly; picking a year
// or a month steps back down. Days in `marks` get a dot, as do the months and
// years that contain them; the legend slot below the grid explains them.
// Selecting the selected day again clears the selection.
const day = defineModel<string | null>({ default: null })
const props = defineProps({
  marks: { type: Object as PropType<Record<string, number>>, default: () => ({}) },
  min: { type: String, default: '' }, // first selectable day, "yyyy-MM-dd"
  max: { type: String, default: '' }, // last selectable day
  utc: { type: Boolean, default: false },
  clearLabel: { type: String, default: 'All days' } // empty for no clear button
})
// the first and last day in view, so the parent can fetch their marks
const emit = defineEmits<{ range: [first: string, last: string] }>()

const tz = useTimeZone()
const today = computed(() => props.utc ? new Date().toISOString().slice(0, 10) : tz.dayKey(Date.now()))
const view = ref<'days' | 'months' | 'years'>('days')
const month = ref((day.value ?? (props.max && props.max < today.value ? props.max : today.value)).slice(0, 7))
watch(day, d => { if (d) { month.value = d.slice(0, 7); view.value = 'days' } })
const year = computed(() => Number(month.value.slice(0, 4)))
const yearsFrom = computed(() => year.value - (year.value % 12)) // twelve years per page

const minMonth = computed(() => props.min.slice(0, 7))
const maxMonth = computed(() => props.max.slice(0, 7))
const pad = (n: number) => String(n).padStart(2, '0')
const markedPrefix = (prefix: string) => Object.keys(props.marks).some(k => k.startsWith(prefix) && props.marks[k])

const fmt = (key: string, opts: Intl.DateTimeFormatOptions) => new Date(`${key}T00:00:00Z`).toLocaleDateString(undefined, { ...opts, timeZone: 'UTC' })
const title = computed(() => view.value == 'days' ? fmt(`${month.value}-01`, { month: 'long', year: 'numeric' })
  : view.value == 'months' ? String(year.value) : `${yearsFrom.value} to ${yearsFrom.value + 11}`)
const weekdays = computed(() => Array.from({ length: 7 }, (_, i) => fmt(addDays('2023-01-01', i), { weekday: 'narrow' })))

// six weeks from the Sunday on or before the first of the month
const dayCells = computed(() => {
  const first = `${month.value}-01`
  const start = addDays(first, -new Date(`${first}T00:00:00Z`).getUTCDay())
  return Array.from({ length: 42 }, (_, i) => {
    const key = addDays(start, i)
    return {
      key, label: String(Number(key.slice(8))), inMonth: key.slice(0, 7) == month.value,
      disabled: (!!props.min && key < props.min) || (!!props.max && key > props.max),
      marked: !!props.marks[key], selected: day.value == key, current: key == today.value,
      aria: fmt(key, { dateStyle: 'full' })
    }
  })
})
const monthCells = computed(() => Array.from({ length: 12 }, (_, i) => {
  const key = `${year.value}-${pad(i + 1)}`
  return {
    key, label: fmt(`${key}-01`, { month: 'short' }), inMonth: true,
    disabled: (!!minMonth.value && key < minMonth.value) || (!!maxMonth.value && key > maxMonth.value),
    marked: markedPrefix(key), selected: day.value?.slice(0, 7) == key, current: today.value.slice(0, 7) == key,
    aria: fmt(`${key}-01`, { month: 'long', year: 'numeric' })
  }
}))
const yearCells = computed(() => Array.from({ length: 12 }, (_, i) => {
  const key = String(yearsFrom.value + i)
  return {
    key, label: key, inMonth: true,
    disabled: (!!props.min && key < props.min.slice(0, 4)) || (!!props.max && key > props.max.slice(0, 4)),
    marked: markedPrefix(key), selected: day.value?.slice(0, 4) == key, current: today.value.slice(0, 4) == key,
    aria: key
  }
}))
const cells = computed(() => view.value == 'days' ? dayCells.value : view.value == 'months' ? monthCells.value : yearCells.value)

// only when the view moves; new marks also rebuild the cells
const range = computed(() => view.value == 'days' ? `${dayCells.value[0].key}/${dayCells.value[41].key}`
  : view.value == 'months' ? `${year.value}-01-01/${year.value}-12-31` : `${yearsFrom.value}-01-01/${yearsFrom.value + 11}-12-31`)
watch(range, r => { const [a, b] = r.split('/'); emit('range', a, b) }, { immediate: true })

function step(n: number) {
  if (view.value == 'days') month.value = addDays(`${month.value}-15`, 30 * n).slice(0, 7)
  else month.value = `${year.value + n * (view.value == 'months' ? 1 : 12)}-${month.value.slice(5)}`
}
const canBack = computed(() => !props.min || (view.value == 'days' ? minMonth.value < month.value
  : view.value == 'months' ? props.min.slice(0, 4) < String(year.value) : props.min.slice(0, 4) < String(yearsFrom.value)))
const canForward = computed(() => !props.max || (view.value == 'days' ? maxMonth.value > month.value
  : view.value == 'months' ? props.max.slice(0, 4) > String(year.value) : props.max.slice(0, 4) > String(yearsFrom.value + 11)))
const zoomOut = () => { view.value = view.value == 'days' ? 'months' : 'years' }

function pick(key: string) {
  if (view.value == 'years') { month.value = `${key}-${month.value.slice(5)}`; view.value = 'months' }
  else if (view.value == 'months') { month.value = key; view.value = 'days' }
  else day.value = day.value == key && props.clearLabel ? null : key
}
</script>

<template>
  <div class="w-72 select-none">
    <div class="flex items-center justify-between mb-2">
      <UButton icon="i-heroicons-chevron-left-20-solid" size="xs" color="gray" variant="ghost" :disabled="!canBack"
        :aria-label="view == 'days' ? 'Previous month' : view == 'months' ? 'Previous year' : 'Earlier years'" @click="step(-1)" />
      <UButton size="xs" color="gray" variant="ghost" :label="title" :disabled="view == 'years'"
        :trailing-icon="view == 'years' ? undefined : 'i-heroicons-chevron-up-20-solid'" class="font-semibold"
        :aria-label="view == 'days' ? 'Show the months' : view == 'months' ? 'Show the years' : title" @click="zoomOut" />
      <UButton icon="i-heroicons-chevron-right-20-solid" size="xs" color="gray" variant="ghost" :disabled="!canForward"
        :aria-label="view == 'days' ? 'Next month' : view == 'months' ? 'Next year' : 'Later years'" @click="step(1)" />
    </div>
    <div v-if="view == 'days'" class="grid grid-cols-7 text-center">
      <span v-for="(w, i) in weekdays" :key="i" class="text-xs text-gray-500 dark:text-gray-400 pb-1">{{ w }}</span>
    </div>
    <div class="grid text-center" :class="view == 'days' ? 'grid-cols-7 gap-y-1' : 'grid-cols-3 gap-2 py-1'">
      <button v-for="c in cells" :key="c.key" type="button" :disabled="c.disabled" :aria-pressed="c.selected"
        :aria-label="c.aria + (c.marked ? ', marked' : '')" @click="pick(c.key)"
        class="relative mx-auto flex items-center justify-center text-sm transition-colors"
        :class="[
          view == 'days' ? 'h-9 w-9 rounded-full' : 'h-12 w-full rounded-md',
          c.selected ? 'bg-primary-500 text-white dark:bg-primary-400 dark:text-gray-900 font-semibold'
            : c.disabled ? 'text-gray-300 dark:text-gray-700 cursor-not-allowed'
              : 'hover:bg-gray-100 dark:hover:bg-gray-800 ' + (c.inMonth ? '' : 'text-gray-400 dark:text-gray-500'),
          c.current && !c.selected ? 'ring-1 ring-primary-500 dark:ring-primary-400' : ''
        ]">
        <span class="leading-none">{{ c.label }}</span>
        <span v-if="c.marked" class="absolute h-1 w-1 rounded-full" :class="[
          view == 'days' ? 'bottom-1' : 'bottom-2',
          c.selected ? 'bg-white dark:bg-gray-900' : 'bg-amber-500 dark:bg-amber-400']" />
      </button>
    </div>
    <div class="mt-2 flex items-center justify-between gap-2 text-xs text-gray-500 dark:text-gray-400 min-h-6">
      <div class="flex flex-wrap items-center gap-3"><slot name="legend" /></div>
      <UButton v-if="day && view == 'days' && clearLabel" size="2xs" color="gray" variant="ghost" :label="clearLabel" @click="day = null" />
    </div>
  </div>
</template>
