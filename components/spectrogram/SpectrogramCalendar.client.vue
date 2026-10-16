<script setup lang="ts">
import type { PropType } from 'vue'

// A month calendar for picking one day, in the time zone chosen on the page.
// Days in `marks` get a dot; the legend slot below the grid explains them.
// Selecting the selected day again clears the selection.
const day = defineModel<string | null>({ default: null })
const props = defineProps({
  marks: { type: Object as PropType<Record<string, number>>, default: () => ({}) },
  min: { type: String, default: '' }, // first selectable day, "yyyy-MM-dd"
  max: { type: String, default: '' } // last selectable day
})
// the first and last day shown, so the parent can fetch their marks
const emit = defineEmits<{ range: [first: string, last: string] }>()

const tz = useTimeZone()
const today = computed(() => tz.dayKey(Date.now()))
const month = ref((day.value ?? (props.max && props.max < today.value ? props.max : today.value)).slice(0, 7))
watch(day, d => { if (d) month.value = d.slice(0, 7) })

const monthLabel = computed(() => {
  const [y, m] = month.value.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString(undefined, { month: 'long', year: 'numeric', timeZone: 'UTC' })
})
const weekdays = computed(() => Array.from({ length: 7 }, (_, i) =>
  new Date(Date.UTC(2023, 0, 1 + i)).toLocaleDateString(undefined, { weekday: 'narrow', timeZone: 'UTC' })))

// six weeks from the Sunday on or before the first of the month
const cells = computed(() => {
  const first = `${month.value}-01`
  const [y, m] = month.value.split('-').map(Number)
  const start = addDays(first, -new Date(Date.UTC(y, m - 1, 1)).getUTCDay())
  return Array.from({ length: 42 }, (_, i) => {
    const key = addDays(start, i)
    return {
      key,
      label: Number(key.slice(8)),
      inMonth: key.slice(0, 7) == month.value,
      disabled: (!!props.min && key < props.min) || (!!props.max && key > props.max),
      marked: !!props.marks[key]
    }
  })
})
// only when the month changes; new marks also rebuild the cells
watch(() => `${cells.value[0].key}/${cells.value[41].key}`, r => { const [a, b] = r.split('/'); emit('range', a, b) }, { immediate: true })

const step = (n: number) => { month.value = addDays(`${month.value}-15`, 30 * n).slice(0, 7) }
const canBack = computed(() => !props.min || props.min.slice(0, 7) < month.value)
const canForward = computed(() => !props.max || props.max.slice(0, 7) > month.value)
const pick = (key: string) => { day.value = day.value == key ? null : key }
const dayText = (key: string) => new Date(`${key}T00:00:00Z`).toLocaleDateString(undefined, { dateStyle: 'full', timeZone: 'UTC' })
</script>

<template>
  <div class="w-full max-w-xs select-none">
    <div class="flex items-center justify-between mb-2">
      <UButton icon="i-heroicons-chevron-left-20-solid" size="xs" color="gray" variant="ghost" :disabled="!canBack"
        aria-label="Previous month" @click="step(-1)" />
      <span class="text-sm font-semibold">{{ monthLabel }}</span>
      <UButton icon="i-heroicons-chevron-right-20-solid" size="xs" color="gray" variant="ghost" :disabled="!canForward"
        aria-label="Next month" @click="step(1)" />
    </div>
    <div class="grid grid-cols-7 gap-y-1 text-center">
      <span v-for="(w, i) in weekdays" :key="i" class="text-xs text-gray-500 dark:text-gray-400 pb-1">{{ w }}</span>
      <button v-for="c in cells" :key="c.key" type="button" :disabled="c.disabled" :aria-pressed="day == c.key"
        :aria-label="dayText(c.key) + (c.marked ? ', marked' : '')" @click="pick(c.key)"
        class="relative mx-auto flex h-9 w-9 flex-col items-center justify-center rounded-full text-sm transition-colors"
        :class="[
          day == c.key ? 'bg-primary-500 text-white dark:bg-primary-400 dark:text-gray-900 font-semibold'
            : c.disabled ? 'text-gray-300 dark:text-gray-700 cursor-not-allowed'
              : 'hover:bg-gray-100 dark:hover:bg-gray-800 ' + (c.inMonth ? '' : 'text-gray-400 dark:text-gray-500'),
          c.key == today && day != c.key ? 'ring-1 ring-primary-500 dark:ring-primary-400' : ''
        ]">
        <span class="leading-none">{{ c.label }}</span>
        <span v-if="c.marked" class="absolute bottom-1 h-1 w-1 rounded-full"
          :class="day == c.key ? 'bg-white dark:bg-gray-900' : 'bg-amber-500 dark:bg-amber-400'" />
      </button>
    </div>
    <div class="mt-2 flex items-center justify-between gap-2 text-xs text-gray-500 dark:text-gray-400 min-h-6">
      <div class="flex flex-wrap items-center gap-3"><slot name="legend" /></div>
      <UButton v-if="day" size="2xs" color="gray" variant="ghost" label="All days" @click="day = null" />
    </div>
  </div>
</template>
