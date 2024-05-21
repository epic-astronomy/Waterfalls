<script setup lang="ts">
definePageMeta({
  layout: 'waterfalls'
})
const route = useRoute()
const { data: page, error: error } = await useAsyncData(route.path, () => queryContent(route.path).findOne())

if (!page.value) {
  throw createError({ statusCode: 404, statusMessage: 'Page not found', fatal: true })
}

useSeoMeta({
  title: page.value.title,
  ogTitle: page.value.title,
  description: page.value.description,
  ogDescription: page.value.description
})

</script>


<template>
<div v-if="page">
  <UDashboardPage>
    <UDashboardPanel grow>
        <UContainer>
          <UPageHero :title="page.hero.title" :description="page.hero.description">
          </UPageHero>
          <UPageGrid>
    <UPageCard v-for="(module, index) in page.cards" :key="index" v-bind="module">
      <template #description>
        <span class="line-clamp-2">{{ module.description }}</span>
      </template>
    </UPageCard>
  </UPageGrid>
        </UContainer>
    </UDashboardPanel>
  </UDashboardPage>
</div>
</template>