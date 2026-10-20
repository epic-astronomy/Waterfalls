// The signed-in user and role, from the API (which checks the Hanko session
// and reads the role Hanko keeps for the user). Loaded once when a page is
// rendered on the server, and again after signing in or out.
export interface AuthUser {
  signed_in: boolean
  email?: string
  role?: 'admin' | 'member' | null
}

export function useAuth() {
  const user = useState<AuthUser | null>('auth-user', () => null)
  const { fastapiBase } = useRuntimeConfig().public
  // the browser's cookies, when rendering on the server (read here, while the request is known)
  const headers = import.meta.server ? useRequestHeaders(['cookie']) : undefined

  async function refresh() {
    try {
      user.value = await $fetch<AuthUser>(fastapiBase + '/auth/me', { headers })
    } catch {
      user.value = { signed_in: false }
    }
    return user.value
  }

  async function logout() {
    try { await useHanko()?.logout() } catch { }
    user.value = { signed_in: false }
    await navigateTo('/')
  }

  const signedIn = computed(() => !!user.value?.signed_in)
  const isAdmin = computed(() => user.value?.role === 'admin')
  return { user, signedIn, isAdmin, refresh, logout }
}
