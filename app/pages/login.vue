<script setup lang="ts">
definePageMeta({
  middleware: ['hanko-logged-out']
})
useSeoMeta({ robots: 'noindex, nofollow' })
</script>
<template>
  <hanko-auth class="center"/>
</template>

<style>
.center {
    display: grid;
    place-items: center;      /* Centers both horizontally and vertically */
    height: 100vh;
  }
</style>
