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
      <UButton disabled label="Sign in" color="gray" to="/login" />
      <UButton disabled label="Sign up" icon="i-heroicons-arrow-right-20-solid" trailing to="/signup" class="hidden lg:flex" />
    </template>

    <template #panel>
      <UNavigationTree :links="mapContentNavigation(navigation)" default-open />
    </template>
  </UHeader>
</template>