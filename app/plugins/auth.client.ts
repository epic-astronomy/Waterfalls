// Keeps the signed-in state in step with Hanko in the browser: signing in
// (wherever Hanko then sends the visitor), signing out and an expired session
// update the menus and admin-only links at once, without reloading the page
export default defineNuxtPlugin(() => {
  const hanko = useHanko()
  if (!hanko) return
  const auth = useAuth()
  hanko.onSessionCreated(() => { auth.refresh() })
  hanko.onUserLoggedOut(() => { auth.user.value = { signed_in: false } })
  hanko.onSessionExpired(() => { auth.user.value = { signed_in: false } })
  hanko.onUserDeleted(() => { auth.user.value = { signed_in: false } })
})
