<script setup lang="ts">
// The header bar of a page, used for its controls or current selection
// rather than a title (the sidebar names the page). The contents sit in a
// rounded box styled like the cards below; the menu button for small screens
// stays at its left. While the sidebar is hidden (its own header has the button
// that hides it), a button here shows it again ([).
const { isSidebarHidden, toggleSidebar } = useDashboard()
</script>

<template>
  <UDashboardNavbar :ui="{
    root: 'h-auto min-h-(--ui-header-height) py-2 border-b-0 relative',
    left: 'flex-1 flex items-stretch gap-1.5 min-w-0'
  }">
    <template #left>
      <UTooltip v-if="isSidebarHidden" text="Show the sidebar" :kbds="['[']" class="hidden lg:flex">
        <UButton color="neutral" variant="ghost" class="self-center" aria-label="Show the sidebar"
          icon="i-heroicons-chevron-double-right" @click="toggleSidebar" />
      </UTooltip>
      <div class="flex-1 min-w-0 flex flex-wrap items-center justify-between gap-x-6 gap-y-2 px-3 py-2
        bg-default ring-1 ring-default rounded-md shadow">
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
