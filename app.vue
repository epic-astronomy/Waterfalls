<script setup lang="ts">
const colorMode = useColorMode()
import { useFavicon, usePreferredDark } from '@vueuse/core'

const color = computed(() => colorMode.value === 'dark' ? '#111827' : 'white')
const isDark = usePreferredDark()
const favicon = computed(() => colorMode.value === 'dark' ? '/favicon-dark.png' : '/favicon-light.png')

useFavicon(favicon, {
    rel: 'icon'
})

const route = useRoute()
const { siteUrl } = useRuntimeConfig().public

// One canonical URL per page: no query string, no trailing slash, always the apex host
const canonicalUrl = computed(() => siteUrl + (route.path === '/' ? '/' : route.path.replace(/\/+$/, '')))

const structuredData = {
  '@context': 'https://schema.org',
  '@graph': [
    {
      '@type': 'Organization',
      '@id': `${siteUrl}/#organization`,
      name: 'EPIC Astronomy',
      url: `${siteUrl}/`,
      logo: `${siteUrl}/favicon-light.png`,
      description: 'Developers of the E-field Parallel Imaging Correlator (EPIC), a real-time all-sky imager for the Long Wavelength Array radio telescope.',
      sameAs: ['https://github.com/epic-astronomy', 'https://livetv.epic-astronomy.org']
    },
    {
      '@type': 'WebSite',
      '@id': `${siteUrl}/#website`,
      name: 'EPIC Astronomy',
      url: `${siteUrl}/`,
      publisher: { '@id': `${siteUrl}/#organization` },
      inLanguage: 'en'
    }
  ]
}

useHead({
  meta: [
    { charset: 'utf-8' },
    { name: 'viewport', content: 'width=device-width, initial-scale=1' },
    { key: 'theme-color', name: 'theme-color', content: color },
    { name: "google-site-verification", content: "yjy61BTcmwKlPO4KVYb_a_PL9M50afpwRF5wpnwqPFw"}
  ],
  link: [
    { rel: 'icon', href: colorMode.value=='dark' ? '/favicon-dark.png' : '/favicon-light.png' },
    { key: 'canonical', rel: 'canonical', href: canonicalUrl }
  ],
  script: [
    { key: 'structured-data', type: 'application/ld+json', innerHTML: JSON.stringify(structuredData) }
  ],
  htmlAttrs: {
    lang: 'en'
  },
})

useSeoMeta({
  titleTemplate: (title) => title ? `${title} | EPIC Astronomy` : 'EPIC Astronomy',
  ogSiteName: 'EPIC Astronomy',
  ogType: 'website',
  ogUrl: canonicalUrl,
  ogImage: `${siteUrl}/social-card.png`,
  twitterImage: `${siteUrl}/social-card.png`,
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
