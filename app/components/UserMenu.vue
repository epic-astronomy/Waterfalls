<script setup lang="ts">
// Sign in, or the signed-in user's menu: the user list for admins, the
// account page, and signing out
import type { DropdownMenuItem } from '@nuxt/ui'

const props = withDefaults(defineProps<{ block?: boolean }>(), { block: false })
const auth = useAuth()
const route = useRoute()

const roleLabel: Record<string, string> = { admin: 'Admin', member: 'Member' }
const items = computed<DropdownMenuItem[][]>(() => [
  [{ label: auth.user.value?.email ?? '', type: 'label' as const },
    { label: roleLabel[auth.user.value?.role ?? ''] ?? 'No role', type: 'label' as const }],
  [...(auth.isAdmin.value ? [{ label: 'Users', icon: 'i-heroicons-users', to: '/waterfalls/admin/users' }] : []),
    { label: 'Account', icon: 'i-heroicons-key', to: '/profile' }],
  [{ label: 'Sign out', icon: 'i-heroicons-arrow-right-on-rectangle', onSelect: () => auth.logout() }]
])
</script>

<template>
  <UDropdownMenu v-if="auth.signedIn.value" :items="items" :content="{ align: 'end' }">
    <UButton color="neutral" variant="ghost" icon="i-heroicons-user-circle" :label="auth.user.value?.email"
      trailing-icon="i-heroicons-chevron-down-20-solid" :block="props.block" :class="props.block ? 'justify-start' : ''"
      :ui="{ label: 'truncate' }" />
  </UDropdownMenu>
  <UButton v-else color="neutral" variant="ghost" icon="i-heroicons-arrow-left-on-rectangle" label="Sign in"
    :block="props.block" :class="props.block ? 'justify-start' : ''"
    :to="{ path: '/login', query: { redirect: route.fullPath } }" />
</template>
