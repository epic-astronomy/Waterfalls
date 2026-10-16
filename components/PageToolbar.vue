<script setup lang="ts">
// The header bar of a page, used for its controls or current selection
// rather than a title (the sidebar names the page). The contents sit in a
// rounded box styled like the cards below; the menu button for small screens
// stays at its left.
</script>

<template>
  <UDashboardNavbar :ui="{
    wrapper: 'h-auto min-h-[--header-height] py-2 border-b-0 relative',
    left: 'flex-1 flex items-stretch gap-1.5 min-w-0'
  }">
    <template #left>
      <div class="flex-1 min-w-0 flex flex-wrap items-center justify-between gap-x-6 gap-y-2 px-3 py-2
        bg-white dark:bg-gray-900 ring-1 ring-gray-200 dark:ring-gray-800 rounded-md shadow">
        <div class="flex flex-wrap items-center gap-x-5 gap-y-2 min-w-0">
          <slot />
        </div>
        <div v-if="$slots.right" class="ml-auto flex items-center gap-2 shrink-0">
          <slot name="right" />
        </div>
      </div>
    </template>
  </UDashboardNavbar>
</template>
