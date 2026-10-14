<script setup lang="ts">
import type { ParsedContent } from '@nuxt/content/dist/runtime/types'

const { data: navigation } = await useAsyncData('navigation', () => fetchContentNavigation(), { default: () => [] })
// Versioned by build so browsers never reuse a search index cached from an earlier deployment
const buildId = useAppConfig().nuxt?.buildId
const { data: files } = useLazyFetch<ParsedContent[]>('/api/search.json', { query: { v: buildId }, default: () => [], server: false })

provide('navigation', navigation)
</script>

<template>
  <div>
    <Header />

    <UMain>
      <slot />
    </UMain>

    <Footer />

    <ClientOnly>
      <LazyUContentSearch :files="files" :navigation="navigation" />
    </ClientOnly>
  </div>
</template>