<script setup lang="ts">
import type { DropdownMenuItem } from '@nuxt/ui'

const hanko = useHanko()
const loggedIn = ref(false)
const emailId = ref<string | undefined>('')
const route = useRoute()

async function initUser() {
  if (!hanko) return
  if ((await hanko.validateSession()).is_valid) {
    loggedIn.value = true
    const user = await hanko.getCurrentUser()
    emailId.value = user?.emails?.find(e => e.is_primary)?.address?.split('@')[0]
  }
}

onMounted(initUser)

const userDropdownItems: DropdownMenuItem[][] = [[{
  label: 'Profile',
  to: '/profile',
  icon: 'i-material-symbols-account-circle'
}, {
  label: 'Logout',
  onSelect: logout,
  icon: 'i-material-symbols-logout'
}]]

function login() {
  navigateTo({ path: '/login', query: { redirect: route.path } })
}

async function logout() {
  await hanko?.logout()
  loggedIn.value = false
  emailId.value = ''
}
</script>

<template>
  <hanko-events @on-session-created="initUser()" />
  <UButton v-if="!loggedIn" label="Sign in" icon="i-heroicons-arrow-right-20-solid" trailing class="hidden lg:flex"
    @click="login" />
  <UDropdownMenu v-else :items="userDropdownItems">
    <UButton color="neutral" variant="outline" :label="emailId" trailing-icon="i-heroicons-chevron-down-20-solid" />
  </UDropdownMenu>
</template>
