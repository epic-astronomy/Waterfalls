import { h } from 'vue'
import { UButton } from '#components'

export interface ManualSort { column: string, direction: 'asc' | 'desc' }

// A table column header that sorts by its column on the server: ascending
// first, then descending on a second click
export function sortHeader(sort: Ref<ManualSort>, key: string, label: string) {
  return () => {
    const on = sort.value.column == key
    return h(UButton, {
      color: 'neutral', variant: 'ghost', label, class: '-mx-2.5 font-semibold',
      trailingIcon: on ? (sort.value.direction == 'asc' ? 'i-heroicons-bars-arrow-up-20-solid' : 'i-heroicons-bars-arrow-down-20-solid')
        : 'i-heroicons-arrows-up-down-20-solid',
      onClick: () => { sort.value = { column: key, direction: on && sort.value.direction == 'asc' ? 'desc' : 'asc' } }
    })
  }
}

// the classes of a selected table row
export const selectedRowClass = 'bg-primary-50 dark:bg-primary-400/15'
