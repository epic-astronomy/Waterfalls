import { queryCollection } from '@nuxt/content/server'

// Application pages that are not backed by a content file
const staticPaths = [
  '/',
  '/publications',
  '/waterfalls',
  '/waterfalls/spectrograms',
  '/waterfalls/spectrograms/lwasv',
  '/waterfalls/spectrograms/dailydigest',
  '/waterfalls/spectrograms/frb',
  '/waterfalls/spectrograms/skymon',
  '/waterfalls/spectrograms/skymon-catalogue'
]

export default defineEventHandler(async (event) => {
  const { siteUrl } = useRuntimeConfig().public

  const docs = await queryCollection(event, 'docs').select('path').all()
  const docPaths = docs.map(d => d.path).filter(p => p.startsWith('/docs/'))

  const paths = [...new Set([...staticPaths, ...docPaths])].sort()
  const urls = paths
    .map(p => `  <url><loc>${siteUrl}${p === '/' ? '/' : p}</loc></url>`)
    .join('\n')

  setResponseHeader(event, 'content-type', 'application/xml; charset=utf-8')
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`
})
