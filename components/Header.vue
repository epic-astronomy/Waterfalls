<script setup lang="ts">
import type { NavItem } from '@nuxt/content/dist/runtime/types'

const navigation = inject<Ref<NavItem[]>>('navigation', ref([]))


const links = [{
  label: 'Docs',
  to: '/docs'
}, {
  label: 'Publications',
  to: '/publications'
}, {
  label: 'Members',
  to: '/members'
}, {
  label: 'Blog',
  to: '/blog'
}]


</script>

<template>
  <UHeader :links="links">
    <template #logo>
      EPIC Astronomy
    </template>

    <template #right>
      <!-- <UButton label="Sign in"  color="gray" to="/login" /> -->
      <UserMngmnt></UserMngmnt>
    </template>

    <template #panel>
      <UNavigationTree :links="mapContentNavigation(navigation)" default-open />
    </template>
  </UHeader>
</template>