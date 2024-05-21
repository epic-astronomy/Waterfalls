<script setup lang="ts">
const route = useRoute()

const { data: page } = await useAsyncData(route.path, () => queryContent(route.path).findOne())
if (!page.value) {
  throw createError({ statusCode: 404, statusMessage: 'Page not found', fatal: true })
}


useSeoMeta({
  title: 'Spectrogram ' + page.value.title,
  ogTitle: page.value.title,
  description: page.value.description,
  ogDescription: page.value.description
})

// defineOgImage({
//   component: 'Saas',
//   title: page.value.title,
//   description: page.value.description
// })

const headline = computed(() => findPageHeadline(page.value!))
</script>

<template>
  <UDashboardPanelContent>
    <UPage v-if="page">
      <UPageHeader :title="page.title" :description="page.description" :links="page.links" :headline="headline" />

      <UPageBody prose>
        <ContentRenderer v-if="page.body" :value="page" />
      </UPageBody>

      <template v-if="page.toc !== false" #right>
        <UContentToc :links="page.body?.toc?.links" />
      </template>
    </UPage>
  </UDashboardPanelContent>
</template>