<script setup lang="ts">
const route = useRoute()
const appConfig = useAppConfig()
const { isHelpSlideoverOpen, isSidebarHidden, toggleSidebar } = useDashboard()

const links = [{
  id: 'home',
  label: 'Home',
  icon: 'i-heroicons-home',
  to: '/waterfalls',
  tooltip: {
    text: 'Home',
    shortcuts: ['G', 'H']
  }
}, {
  id: 'spectrograms',
  label: 'Spectrograms',
  icon: 'i-material-symbols-key-visualizer',
  to: '/waterfalls/spectrograms',
  children: [{
    label: 'Instructions',
    to: '/waterfalls/spectrograms/',
    exact: true
  }, {
    label: 'LWA-SV',
    to: '/waterfalls/spectrograms/lwasv'
  },{
    label:'Daily Digest',
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
  }
    // ,{
    //   label:'Plotly test',
    //   to: '/waterfalls/spectrograms/plotly'
    // }
  ],
  tooltip: {
    text: 'Settings',
    shortcuts: ['G', 'S']
  }
}]

const footerLinks = [{
  label: 'Help & Support',
  icon: 'i-heroicons-question-mark-circle',
  click: () => isHelpSlideoverOpen.value = true
}]

const groups = [{
  key: 'links',
  label: 'Go to',
  commands: links.map(link => ({ ...link, shortcuts: link.tooltip?.shortcuts }))
}]

</script>

<template>
  <UDashboardLayout>
    <!-- hidden from the toolbar's button (PageToolbar); small screens keep the slide-over -->
    <UDashboardPanel :width="250" :resizable="{ min: 250, max: 300 }" collapsible
      :class="isSidebarHidden ? 'lg:!hidden' : ''">
      <UDashboardNavbar class="!border-transparent" :ui="{ left: 'flex-1' }">
        <template #left>
          <AppsDropdown />
        </template>
        <!-- hides the sidebar on wide screens ([); PageToolbar shows it again -->
        <template #right>
          <UTooltip text="Hide the sidebar" :shortcuts="['[']" class="hidden lg:flex">
            <UButton color="gray" variant="ghost" icon="i-heroicons-chevron-double-left" aria-label="Hide the sidebar"
              @click="toggleSidebar" />
          </UTooltip>
        </template>
      </UDashboardNavbar>

      <UDashboardSidebar>
        <template #header>
          <UDashboardSearchButton />
        </template>

        <UDashboardSidebarLinks :links="links" />

        <div class="flex-1" />

        <UDivider class="sticky bottom-0" />
        <UColorModeSelect />
        <template #footer>
          <!-- ~/components/UserDropdown.vue -->

          <UDashboardSidebarLinks :links="footerLinks" />
        </template>
      </UDashboardSidebar>
    </UDashboardPanel>

    <slot />

    <!-- ~/components/HelpSlideover.vue -->
    <HelpSlideover />
    <!-- ~/components/NotificationsSlideover.vue -->
    <!-- <NotificationsSlideover /> -->

    <ClientOnly>
      <LazyUDashboardSearch :groups="groups" />
    </ClientOnly>
  </UDashboardLayout>

</template>