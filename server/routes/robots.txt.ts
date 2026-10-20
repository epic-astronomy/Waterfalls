export default defineEventHandler((event) => {
  const { siteUrl } = useRuntimeConfig().public
  setResponseHeader(event, 'content-type', 'text/plain; charset=utf-8')
  return [
    'User-agent: *',
    'Allow: /',
    'Disallow: /api/',
    'Disallow: /waterfalls/admin/',
    'Disallow: /login',
    'Disallow: /profile',
    '',
    `Sitemap: ${siteUrl}/sitemap.xml`,
    ''
  ].join('\n')
})
