<script setup lang="ts">
const colorMode = useColorMode()
import { useFavicon, usePreferredDark } from '@vueuse/core'

const color = computed(() => colorMode.value === 'dark' ? '#111827' : 'white')
const isDark = usePreferredDark()
const favicon = computed(() => colorMode.value === 'dark' ? '/favicon-dark.png' : '/favicon-light.png')

useFavicon(favicon, {
    rel: 'icon'
})

useHead({
  meta: [
    { charset: 'utf-8' },
    { name: 'viewport', content: 'width=device-width, initial-scale=1' },
    { key: 'theme-color', name: 'theme-color', content: color }
  ],
  link: [
    { rel: 'icon', href: colorMode.value=='dark' ? '/favicon-dark.png' : '/favicon-light.png' }
  ],
  htmlAttrs: {
    lang: 'en'
  },
})

useSeoMeta({
  titleTemplate: 'EPIC Astronomy - %s ',
  ogImage: 'https://epic-astronomy.org/social-card.png',
  twitterImage: 'https://epic-astronomy.org/social-card.png',
  twitterCard: 'summary_large_image'
})
</script>

<template>
  <div>
    <NuxtLoadingIndicator />
    <UNotifications :ui="{notifications:{position:'top-0 end-0'}}"/>
    <NuxtLayout>
      <NuxtPage />
    </NuxtLayout>
  </div>
</template>
