<script setup lang="ts">
const route = useRoute()

const { data: page } = await useAsyncData(route.path, () => queryCollection('spectrograms').path('/waterfalls/spectrograms').first())
if (!page.value) {
  throw createError({ statusCode: 404, statusMessage: 'Page not found', fatal: true })
}

useSeoMeta({
  title: 'Spectrogram ' + page.value.title,
  ogTitle: page.value.title,
  description: page.value.description,
  ogDescription: page.value.description
})
</script>

<template>
  <UDashboardPanel id="spectrogram-instructions">
    <template #body>
      <UPage v-if="page">
        <UPageHeader :title="page.title" :description="page.description" headline="Spectrograms" />

        <UPageBody>
          <ContentRenderer v-if="page.body" :value="page" />
        </UPageBody>

        <template v-if="page.body?.toc?.links?.length" #right>
          <UContentToc :links="page.body.toc.links" />
        </template>
      </UPage>
    </template>
  </UDashboardPanel>
</template>
