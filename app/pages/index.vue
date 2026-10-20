<script setup lang="ts">
const { data: page, error: error } = await useAsyncData('index', () => queryCollection('landing').path('/').first())

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
    <UPageHero :description="page.hero.description" :links="page.hero.links">
      <div class="absolute inset-0 landing-grid -z-10 [mask-image:radial-gradient(100%_100%_at_top_right,white,transparent)]" />
      <template #headline>
        <UBadge variant="subtle" size="lg" class="relative rounded-full font-semibold">
          <NuxtLink to="/waterfalls/spectrograms/dailydigest" target="_self" class="focus:outline-none" tabindex="-1">
            <span class="absolute inset-0" aria-hidden="true" />
          </NuxtLink>

          New: Daily Digest

          <UIcon name="i-heroicons-arrow-top-right-on-square-20-solid" class="ml-1 w-4 h-4 pointer-events-none" />
        </UBadge>
      </template>
      <template #title>
        A <span class="text-primary block lg:inline-block">real-time</span> view of the
        <br>
        Low-Frequency Radio Universe
      </template>
    </UPageHero>
    <UPageSection :ui="{ container: 'py-0 sm:py-0 lg:py-0 pb-16 sm:pb-16 lg:pb-24' }">
      <UPageGrid>
        <UPageCard v-for="(card, index) in page.hero.cards" :key="index" :title="card.title" :icon="card.icon"
          :target="card.target" :to="card.to" spotlight>
          <template #description>
            <span class="line-clamp-2">{{ card.description }}</span>
          </template>
        </UPageCard>
      </UPageGrid>
    </UPageSection>
  </div>
</template>

<style scoped>
.landing-grid {
  background-size: 60px 60px;
  background-image:
    linear-gradient(to right, var(--ui-color-neutral-200) 1px, transparent 1px),
    linear-gradient(to bottom, var(--ui-color-neutral-200) 1px, transparent 1px);
}
.dark {
  .landing-grid {
    background-image:
      linear-gradient(to right, var(--ui-color-neutral-800) 1px, transparent 1px),
      linear-gradient(to bottom, var(--ui-color-neutral-800) 1px, transparent 1px);
  }
}
</style>