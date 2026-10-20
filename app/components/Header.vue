<script setup lang="ts">
import type { ContentNavigationItem } from '@nuxt/content'
import type { NavigationMenuItem } from '@nuxt/ui'

const navigation = inject<Ref<ContentNavigationItem[]>>('navigation', ref([]))
const route = useRoute()

const links = computed<NavigationMenuItem[]>(() => [{
  label: 'Docs',
  to: '/docs',
  active: route.path.startsWith('/docs')
}, {
  label: 'Waterfalls',
  to: '/waterfalls'
}, {
  label: 'Publications',
  to: '/publications'
}])
</script>

<template>
  <UHeader>
    <template #title>
      EPIC Astronomy
    </template>

    <UNavigationMenu :items="links" variant="link" />

    <template #right>
      <!-- <UserMngmnt /> -->
    </template>

    <template #body>
      <UNavigationMenu :items="links" orientation="vertical" class="-mx-2.5" />
      <USeparator type="dashed" class="my-6" />
      <UContentNavigation :navigation="navigation" highlight />
    </template>
  </UHeader>
</template>
