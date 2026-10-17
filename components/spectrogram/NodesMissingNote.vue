<script setup lang="ts">
// A short note when some imaging nodes did not answer, naming their bands
import type { PropType } from 'vue'
import { missingNote, type NodeFlags } from '~/lib/nodes'

const props = defineProps({
  flags: { type: Object as PropType<NodeFlags | null>, default: null }
})
const text = computed(() => missingNote(props.flags))
</script>

<template>
  <p v-if="text" class="flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-400" role="status">
    <UIcon name="i-heroicons-exclamation-triangle" class="h-4 w-4 shrink-0" />
    <span>{{ text }}</span>
  </p>
</template>
