<script setup lang="ts">
// The signed-in user's email, passkeys and sessions (Hanko's profile element)
definePageMeta({
  middleware: ['hanko-logged-in']
})
useSeoMeta({ title: 'Account', robots: 'noindex, nofollow' })
</script>

<template>
  <UContainer class="py-16 sm:py-24">
    <div class="mx-auto max-w-xl">
      <UCard>
        <template #header>
          <h1 class="text-xl font-semibold text-highlighted">Account</h1>
          <p class="mt-1 text-sm text-muted">Your email address, passkeys and signed-in sessions.</p>
        </template>
        <hanko-profile class="hanko-theme" />
      </UCard>
    </div>
  </UContainer>
</template>
