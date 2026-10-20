// Passes /api/v1 to the FastAPI backend, whose address is set at run time
// (NUXT_API_ORIGIN), so one image serves wherever the backend runs
export default defineEventHandler((event) => {
  const { apiOrigin } = useRuntimeConfig(event)
  return proxyRequest(event, apiOrigin.replace(/\/+$/, '') + event.path)
})
