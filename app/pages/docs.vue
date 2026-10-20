<script setup lang="ts">
import type { ContentNavigationItem } from '@nuxt/content'

const navigation = inject<Ref<ContentNavigationItem[]>>('navigation', ref([]))

const links = computed(() => navigation.value.find(item => item.path === '/docs')?.children ?? [])

useSeoMeta({
  title: 'Docs',
  ogTitle: 'Docs',
  description: 'Documentation on EPIC Astronomy group',
  ogDescription: 'Documentation on EPIC Astronomy group'
})
</script>

<template>
  <UContainer>
    <UPage>
      <template #left>
        <UPageAside>
          <template #top>
            <UContentSearchButton :collapsed="false" class="w-full" />
          </template>

          <UContentNavigation :navigation="links" highlight />
        </UPageAside>
      </template>

      <NuxtPage />
    </UPage>
  </UContainer>
</template>
