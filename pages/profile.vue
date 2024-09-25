<script setup lang="ts">
definePageMeta({
  middleware: ['hanko-logged-in']
})
</script>
<template>
  <hanko-profile class="center"/>
</template>
<style>
.center {
    display: grid;
    place-items: center;      /* Centers both horizontally and vertically */
    height: 100vh;
  }
</style>
