<script setup lang="ts">
const { data: page, error: error } = await useAsyncData('index', () => queryContent('/').findOne())

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
    <ULandingHero
      :description="page.hero.description" :links="page.hero.links" >
      <div class="absolute inset-0 landing-grid z-[-1] [mask-image:radial-gradient(100%_100%_at_top_right,white,transparent)]" />
      <template #title>
        A <span class="text-primary block lg:inline-block">real-time</span> view of the
        <br> 
        Low-Frequency Radio Universe
      </template>
      <template #bottom>
        
      </template>
    </ULandingHero>
    <ULandingSection :ui="{wrapper: 'py-0 sm:py-0'}">
      <UPageGrid>
    <ULandingCard v-for="(card, index) in page.hero.cards" :key="index" :title="card.title" :icon="card.icon" :target="card.target" :external="card.external" :to="card.to">
      <template #description>
        <span class="line-clamp-2">{{ card.description }}</span>
      </template>
      <template #icon>
        <Icon :name="card.icon" class="mb-2 pointer-events-none w-8 h-8 flex-shrink-0 text-gray-900 dark:text-white"></Icon>
      </template>
    </ULandingCard> 
  </UPageGrid>
    </ULandingSection>
  </div>
</template>

<style scoped>
.landing-grid {
  background-size: 60px 60px;
  background-image:
    linear-gradient(to right, rgb(var(--color-gray-200)) 1px, transparent 1px),
    linear-gradient(to bottom, rgb(var(--color-gray-200)) 1px, transparent 1px);
}
.dark {
  .landing-grid {
    background-image:
      linear-gradient(to right, rgb(var(--color-gray-800)) 1px, transparent 1px),
      linear-gradient(to bottom, rgb(var(--color-gray-800)) 1px, transparent 1px);
  }
}
</style>