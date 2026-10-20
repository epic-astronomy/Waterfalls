<script setup lang="ts">
// The invited users of the website and their roles, for admins: invite by
// email (an account is made and an invitation sent), change a role, remove.
// Admins see the all-sky monitor, its catalogue and this page, and review
// candidates; members are signed in for the data. An admin cannot change
// their own role or remove themselves.
import type { TableColumn } from '@nuxt/ui'

definePageMeta({ layout: 'waterfalls', middleware: 'admin' })
useSeoMeta({ title: 'Users', robots: 'noindex, nofollow' })

interface User { id: string, email: string, role: 'admin' | 'member' | null, created_at: string }

const { fastapiBase } = useRuntimeConfig().public
const toast = useToast()
const tz = useTimeZone()
const auth = useAuth()

const roles = [{ label: 'Member', value: 'member' }, { label: 'Admin', value: 'admin' }]
const roleText: Record<string, string> = { admin: 'Admins see the all-sky monitor and its catalogue, review candidates and manage users.', member: 'Members are signed in for the data of the website.' }

const { data: users, pending, refresh, error } = await useLazyFetch<User[]>(fastapiBase + '/admin/users', {
  default: () => [], server: false
})
const errorText = (e: any) => e?.data?.detail ?? e?.message ?? 'The request failed'

// invite
const email = ref('')
const role = ref<'member' | 'admin'>('member')
const notify = ref(true)
const inviting = ref(false)
async function invite() {
  inviting.value = true
  try {
    const r = await $fetch<{ user: User, invited: boolean }>(fastapiBase + '/admin/users', {
      method: 'POST', body: { email: email.value, role: role.value, notify: notify.value }
    })
    toast.add({
      title: `${r.user.email} added as ${r.user.role}`, color: 'success', icon: 'i-heroicons-check-circle',
      description: notify.value ? (r.invited ? 'The invitation email was sent.' : 'The invitation email could not be sent; tell them to sign in with this address.') : undefined
    })
    email.value = ''
    await refresh()
  } catch (e) {
    toast.add({ title: 'Not added', description: errorText(e), color: 'error', icon: 'i-heroicons-exclamation-circle' })
  } finally {
    inviting.value = false
  }
}

// change a role
const busy = ref<string | null>(null)
async function setRole(u: User, value: 'admin' | 'member') {
  if (u.role == value) return
  busy.value = u.id
  try {
    await $fetch(fastapiBase + `/admin/users/${u.id}`, { method: 'PATCH', body: { role: value } })
    toast.add({ title: `${u.email} is now ${value == 'admin' ? 'an admin' : 'a member'}`, color: 'success', icon: 'i-heroicons-check-circle' })
  } catch (e) {
    toast.add({ title: 'Role not changed', description: errorText(e), color: 'error', icon: 'i-heroicons-exclamation-circle' })
  } finally {
    busy.value = null
    await refresh()
  }
}

// remove, after a confirmation
const removing = ref<User | null>(null)
const removeOpen = computed({ get: () => !!removing.value, set: (v: boolean) => { if (!v) removing.value = null } })
async function remove() {
  const u = removing.value
  if (!u) return
  busy.value = u.id
  try {
    await $fetch(fastapiBase + `/admin/users/${u.id}`, { method: 'DELETE' })
    toast.add({ title: `${u.email} removed`, color: 'success', icon: 'i-heroicons-check-circle' })
  } catch (e) {
    toast.add({ title: 'Not removed', description: errorText(e), color: 'error', icon: 'i-heroicons-exclamation-circle' })
  } finally {
    busy.value = null
    removing.value = null
    await refresh()
  }
}

const isSelf = (u: User) => u.email == auth.user.value?.email
const columns: TableColumn<User>[] = [
  { accessorKey: 'email', header: 'Email' },
  { accessorKey: 'role', header: 'Role' },
  { accessorKey: 'created_at', header: 'Added' },
  { id: 'actions', header: '' }
]
</script>

<template>
  <UDashboardPanel id="admin-users">
    <template #header>
      <PageToolbar>
        <span class="text-sm text-muted">Users</span>
        <template #right><TimeZoneToggle /></template>
      </PageToolbar>
    </template>
    <template #body>
      <div class="max-w-4xl space-y-4">
        <UCard>
          <template #header>
            <h2 class="font-medium text-highlighted">Invite</h2>
            <p class="mt-1 text-sm text-muted">
              Sign-up is closed: an account is made here for an email address, and its owner signs in with a code sent
              to that address. {{ roleText[role] }}
            </p>
          </template>
          <form class="flex flex-wrap items-center gap-2" @submit.prevent="invite">
            <UInput v-model="email" type="email" required placeholder="name@example.org" icon="i-heroicons-envelope"
              class="w-72" aria-label="Email address" />
            <USelect v-model="role" :items="roles" class="w-32" aria-label="Role" />
            <UCheckbox v-model="notify" label="Send an invitation email" />
            <UButton type="submit" label="Invite" icon="i-heroicons-user-plus" :loading="inviting" :disabled="!email" />
          </form>
        </UCard>

        <UCard :ui="{ body: 'p-0 sm:p-0' }">
          <UAlert v-if="error" color="error" variant="soft" icon="i-heroicons-exclamation-triangle" class="m-3"
            :title="errorText(error)" />
          <UTable :data="users" :columns="columns" :loading="pending" loading-color="primary" loading-animation="carousel"
            empty="No users yet." class="my-0">
            <template #email-cell="{ row }">
              <span class="text-highlighted">{{ row.original.email }}</span>
              <UBadge v-if="isSelf(row.original)" label="you" color="neutral" variant="subtle" size="sm" class="ml-2" />
            </template>
            <template #role-cell="{ row }">
              <UBadge v-if="isSelf(row.original) || !row.original.role" :label="row.original.role == 'admin' ? 'Admin' : row.original.role == 'member' ? 'Member' : 'No role'"
                :color="row.original.role == 'admin' ? 'primary' : 'neutral'" variant="subtle" size="md" />
              <USelect v-if="!isSelf(row.original)" :model-value="row.original.role ?? undefined" :items="roles" size="sm"
                class="w-28" :class="!row.original.role ? 'ml-2' : ''" :disabled="busy == row.original.id"
                placeholder="Set role" @update:model-value="(v: any) => setRole(row.original, v)" />
            </template>
            <template #created_at-cell="{ row }">
              {{ tz.dateTime(row.original.created_at) }} {{ tz.zoneName(row.original.created_at) }}
            </template>
            <template #actions-cell="{ row }">
              <div class="flex justify-end">
                <UButton v-if="!isSelf(row.original)" color="error" variant="ghost" size="sm" icon="i-heroicons-trash"
                  :aria-label="`Remove ${row.original.email}`" :loading="busy == row.original.id"
                  @click="removing = row.original" />
              </div>
            </template>
          </UTable>
        </UCard>
      </div>

      <UModal v-model:open="removeOpen" title="Remove this user?"
        :description="removing ? `${removing.email} will no longer be able to sign in. They can be invited again later.` : ''">
        <template #footer>
          <div class="flex justify-end gap-2 w-full">
            <UButton color="neutral" variant="outline" label="Cancel" @click="removing = null" />
            <UButton color="error" label="Remove" icon="i-heroicons-trash" @click="remove" />
          </div>
        </template>
      </UModal>
    </template>
  </UDashboardPanel>
</template>
