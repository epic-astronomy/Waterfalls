<script setup lang="ts">
definePageMeta({
  layout: 'waterfalls'
})
const { data: page } = await useAsyncData('waterfalls-home', () => queryCollection('landing').path('/waterfalls').first())

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
  <UDashboardPanel v-if="page" id="waterfalls-home">
    <template #body>
      <UContainer>
        <UPageHero :title="page.hero.title" :description="page.hero.description" />
        <UPageGrid class="pb-12">
          <UPageCard v-for="(module, index) in page.cards" :key="index" :title="module.title" :to="module.to"
            :target="module.target" spotlight>
            <template #description>
              <span class="line-clamp-2">{{ module.description }}</span>
            </template>
          </UPageCard>
        </UPageGrid>
      </UContainer>
    </template>
  </UDashboardPanel>
</template>
