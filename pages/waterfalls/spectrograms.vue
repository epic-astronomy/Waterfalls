<script setup lang="ts">
definePageMeta({
  layout: 'waterfalls'
})
// const route = useRoute()
// const { data: page, error: error } = await useAsyncData(route.path, () => queryContent(route.path).findOne())

// if (!page.value) {
//   throw createError({ statusCode: 404, statusMessage: 'Page not found', fatal: true })
// }

// useSeoMeta({
//   title: page.value.title,
//   ogTitle: page.value.title,
//   description: page.value.description,
//   ogDescription: page.value.description
// })

</script>


<template>
    <UDashboardPage>
      <UDashboardPanel grow>
        <NuxtPage/>
      </UDashboardPanel>
    </UDashboardPage>
</template>