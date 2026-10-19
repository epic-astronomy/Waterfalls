<script setup lang="ts">
// Feedback while something on the all-sky monitor page loads: a moving bar
// and a message that advances every few seconds through the steps given,
// staying on the last one. Rendered on the server too, so it shows before
// the page's scripts have loaded.
const props = withDefaults(defineProps<{ messages: string[], interval?: number, compact?: boolean }>(), { interval: 2500 })
const i = ref(0)
const elapsed = ref(0)
let step: ReturnType<typeof setInterval> | undefined
let clock: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  step = setInterval(() => { if (i.value < props.messages.length - 1) i.value++ }, props.interval)
  clock = setInterval(() => { elapsed.value++ }, 1000)
})
onBeforeUnmount(() => { clearInterval(step); clearInterval(clock) })
</script>

<template>
  <div class="flex flex-col items-center justify-center gap-3 text-center" :class="compact ? 'py-3' : 'py-10'">
    <UProgress animation="carousel" size="xs" class="w-56 max-w-full" />
    <p class="text-sm text-gray-600 dark:text-gray-300">{{ messages[i] }}</p>
    <p v-if="elapsed >= 8" class="text-xs text-gray-500 dark:text-gray-400">Still working, {{ elapsed }} s so far.</p>
  </div>
</template>
