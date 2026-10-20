<script setup lang="ts">
import type { DropdownMenuItem } from '@nuxt/ui'

const apps = [{
  label: 'Waterfalls',
  to: '/waterfalls',
  icon: 'i-material-symbols-waterfall-chart'
}, {
  label: 'EPIC Astronomy',
  icon: 'i-heroicons-home',
  to: '/'
}]

const app = apps[0]!
const items: DropdownMenuItem[][] = [apps]
</script>

<template>
  <UDropdownMenu :items="items" :content="{ align: 'start' }" :ui="{ content: 'w-(--reka-dropdown-menu-trigger-width)' }">
    <UButton color="neutral" variant="ghost" class="w-full data-[state=open]:bg-elevated">
      <UIcon :name="app.icon" class="size-6 text-primary" />
      <span class="truncate text-highlighted text-lg font-semibold">{{ app.label }}</span>
    </UButton>
  </UDropdownMenu>
</template>
