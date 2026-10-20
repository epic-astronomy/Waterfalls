// Pages for admins only: visitors are sent to sign in, and anyone else is
// shown "Page not found", as if the page did not exist. The API checks again.
export default defineNuxtRouteMiddleware(async (to) => {
  const auth = useAuth()
  if (!auth.user.value?.signed_in) await auth.refresh()
  if (!auth.user.value?.signed_in) return navigateTo({ path: '/login', query: { redirect: to.fullPath } })
  if (!auth.isAdmin.value) throw createError({ statusCode: 404, statusMessage: 'Page not found', fatal: true })
})
