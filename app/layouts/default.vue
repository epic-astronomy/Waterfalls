<script setup lang="ts">
const { data: navigation } = await useAsyncData('navigation', () => queryCollectionNavigation('docs'), { default: () => [] })
const { data: files } = useLazyAsyncData('search', () => queryCollectionSearchSections('docs'), { default: () => [], server: false })

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
