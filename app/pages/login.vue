<script setup lang="ts">
// Sign in with Hanko: invited users only. After signing in the visitor
// returns to the page that sent them here (?redirect=), or to the Waterfalls.
definePageMeta({
  middleware: ['hanko-logged-out']
})
useSeoMeta({ title: 'Sign in', robots: 'noindex, nofollow' })

const auth = useAuth()
async function signedIn() {
  await auth.refresh()
}
</script>

<template>
  <UContainer class="py-16 sm:py-24">
    <div class="mx-auto max-w-md">
      <UCard>
        <template #header>
          <h1 class="text-xl font-semibold text-highlighted">Sign in</h1>
          <p class="mt-1 text-sm text-muted">
            For invited members of the EPIC team. A code is sent to your email address; no password is needed.
          </p>
        </template>
        <hanko-events @on-session-created="signedIn" />
        <!-- sign-in only: sign-up is closed, so its link is left out -->
        <hanko-login class="hanko-theme" />
      </UCard>
    </div>
  </UContainer>
</template>

<style>
/* Hanko's elements in the site's colours */
.hanko-theme {
  --color: var(--ui-text-highlighted);
  --color-shade-1: var(--ui-text-muted);
  --color-shade-2: var(--ui-border);
  --brand-color: var(--ui-primary);
  --brand-color-shade-1: var(--ui-color-primary-600);
  --brand-contrast-color: var(--ui-text-inverted);
  --background-color: var(--ui-bg);
  --error-color: var(--ui-error);
  --link-color: var(--ui-primary);
  --font-family: var(--font-sans);
  --border-radius: 0.375rem;
  --container-padding: 0;
  --container-max-width: 100%;
}
</style>
