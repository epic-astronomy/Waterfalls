<script setup lang="ts">
import type { PropType } from 'vue'

// A button that opens the calendar on demand. It shows the chosen day, and
// its cross clears it to list every day again.
const day = defineModel<string | null>({ default: null })
defineProps({
  marks: { type: Object as PropType<Record<string, number>>, default: () => ({}) },
  min: { type: String, default: '' },
  max: { type: String, default: '' }
})
const emit = defineEmits<{ range: [first: string, last: string] }>()

const open = ref(false)
watch(day, () => { open.value = false })
const label = computed(() => day.value
  ? new Date(`${day.value}T00:00:00Z`).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })
  : 'All days')
</script>

<template>
  <div class="flex items-center">
    <UPopover v-model:open="open" :popper="{ placement: 'bottom-start' }">
      <UButton icon="i-heroicons-calendar-days-20-solid" size="xs" :color="day ? 'primary' : 'gray'"
        :variant="day ? 'soft' : 'solid'" :label="label" :trailing-icon="day ? undefined : 'i-heroicons-chevron-down-20-solid'" />
      <template #panel>
        <div class="p-3">
          <SpectrogramCalendar v-model="day" :marks="marks" :min="min" :max="max" @range="(a, b) => emit('range', a, b)">
            <template #legend><slot name="legend" /></template>
          </SpectrogramCalendar>
        </div>
      </template>
    </UPopover>
    <UButton v-if="day" icon="i-heroicons-x-mark-20-solid" size="xs" color="gray" variant="ghost"
      aria-label="Show all days" @click="day = null" />
  </div>
</template>
