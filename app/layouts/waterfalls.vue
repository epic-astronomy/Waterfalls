<script setup lang="ts">
import type { NavigationMenuItem } from '@nuxt/ui'

const { isHelpSlideoverOpen, isSidebarHidden, toggleSidebar } = useDashboard()

const links: NavigationMenuItem[] = [{
  label: 'Home',
  icon: 'i-heroicons-home',
  to: '/waterfalls',
  exact: true
}, {
  label: 'Spectrograms',
  icon: 'i-material-symbols-key-visualizer',
  to: '/waterfalls/spectrograms',
  defaultOpen: true,
  children: [{
    label: 'Instructions',
    to: '/waterfalls/spectrograms',
    exact: true
  }, {
    label: 'LWA-SV',
    to: '/waterfalls/spectrograms/lwasv'
  }, {
    label: 'Daily Digest',
    to: '/waterfalls/spectrograms/dailydigest'
  }, {
    label: 'FRB events',
    to: '/waterfalls/spectrograms/frb'
  }, {
    label: 'All-sky monitor',
    to: '/waterfalls/spectrograms/skymon',
    exact: true
  }, {
    label: 'All-sky catalogue',
    to: '/waterfalls/spectrograms/skymon-catalogue'
  }]
}]

const footerLinks: NavigationMenuItem[] = [{
  label: 'Help & Support',
  icon: 'i-heroicons-question-mark-circle',
  onSelect: () => { isHelpSlideoverOpen.value = true }
}]

const groups = [{
  id: 'links',
  label: 'Go to',
  items: links.flatMap(link => [link, ...(link.children ?? [])]).map(l => ({ label: l.label, icon: l.icon, to: l.to }))
}]
</script>

<template>
  <UDashboardGroup unit="px">
    <!-- hidden from its own button on wide screens; PageToolbar shows it again. Small screens keep the slide-over -->
    <UDashboardSidebar id="waterfalls" :default-size="250" :min-size="250" :max-size="300" resizable
      :class="isSidebarHidden ? 'lg:hidden!' : ''">
      <template #header>
        <AppsDropdown class="flex-1 min-w-0" />
        <UTooltip text="Hide the sidebar" :kbds="['[']" class="hidden lg:flex">
          <UButton color="neutral" variant="ghost" icon="i-heroicons-chevron-double-left" aria-label="Hide the sidebar"
            @click="toggleSidebar" />
        </UTooltip>
      </template>

      <UDashboardSearchButton :collapsed="false" class="w-full" />

      <UNavigationMenu :items="links" orientation="vertical" />

      <div class="flex-1" />

      <USeparator />
      <UColorModeSelect class="w-full" />

      <template #footer>
        <UNavigationMenu :items="footerLinks" orientation="vertical" class="w-full" />
      </template>
    </UDashboardSidebar>

    <slot />

    <HelpSlideover />

    <ClientOnly>
      <LazyUDashboardSearch :groups="groups" />
    </ClientOnly>
  </UDashboardGroup>
</template>
