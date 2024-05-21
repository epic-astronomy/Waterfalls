<script setup lang="ts">
const apps = [{
  label: 'Waterfalls',
  to: '/waterfalls',
  icon: 'i-material-symbols-waterfall-chart',
  iconClass:"text-primary dark:text-primary",
  click: () => {
    app.value = apps[0]
  },
},{
  label: 'EPIC Astronomy',
  icon: 'i-heroicons-home',
  iconClass:"text-primary w-6 h-6 dark:text-primary",
  to:'/',
  click: () => {
    app.value = apps[1]
  }
}]


const app = ref(apps[0])
</script>

<template>
  <UDropdown
    v-slot="{ open }"
    mode="hover"
    :items="[apps]"
    class="w-full"
    :ui="{ width: 'w-full' }"
    :popper="{ strategy: 'absolute' }"
  >
    <UButton :to="app.to" color="gray" variant="ghost" :class="[open && 'bg-gray-50 dark:bg-gray-800']" class="w-full">
      <UIcon :name="app.icon" size="2xs" class="w-6 h-6 text-primary dark:text-primary"/>

      <span class="truncate text-gray-900 text-lg dark:text-white font-semibold">{{ app.label }}</span>
    </UButton>
  </UDropdown>
</template>