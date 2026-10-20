<script setup lang="ts">
import type { NuxtError } from '#app'

const props = defineProps<{ error: NuxtError }>()

useSeoMeta({
  title: props.error.statusMessage,
  description: "Even the Dark Knight can't find what you're looking for. Apologies for the 404, citizen. Let's try a different page!."
})

useHead({
  htmlAttrs: {
    lang: 'en'
  }
})

const { data: navigation } = await useAsyncData('navigation', () => queryCollectionNavigation('docs'), { default: () => [] })
const { data: files } = useLazyAsyncData('search', () => queryCollectionSearchSections('docs'), { default: () => [], server: false })

provide('navigation', navigation)
</script>

<template>
  <UApp>
    <Header />

    <UMain>
      <UContainer>
        <UPage>
          <UError :error="{ ...error, message: 'Even the Dark Knight can\'t find what you\'re looking for. Apologies for the 404, citizen. Let\'s try a different page!' }" />
        </UPage>
      </UContainer>
    </UMain>

    <Footer />

    <ClientOnly>
      <LazyUContentSearch :files="files" :navigation="navigation" />
    </ClientOnly>
  </UApp>
</template>
