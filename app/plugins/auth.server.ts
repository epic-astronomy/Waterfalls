// Who is signed in, before the page is rendered, so menus and admin-only links
// are right from the first paint. Visitors without a session cookie cost nothing.
export default defineNuxtPlugin(async () => {
  const auth = useAuth()
  if (!useRequestHeaders(['cookie']).cookie?.includes('hanko=')) {
    auth.user.value = { signed_in: false }
    return
  }
  await auth.refresh()
})
