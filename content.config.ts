import { defineCollection, defineContentConfig, z } from '@nuxt/content'

const link = z.object({
  label: z.string(),
  icon: z.string().optional(),
  to: z.string(),
  target: z.string().optional(),
  trailing: z.boolean().optional(),
  size: z.string().optional(),
  color: z.string().optional(),
  variant: z.string().optional()
})

const card = z.object({
  title: z.string(),
  description: z.string(),
  icon: z.string().optional(),
  to: z.string(),
  target: z.string().optional(),
  external: z.boolean().optional(),
  class: z.string().optional()
})

export default defineContentConfig({
  collections: {
    // the site's home page and the Waterfalls home page
    landing: defineCollection({
      type: 'page',
      source: [{ include: '0.index.yml' }, { include: '2.waterfalls/0.index.yml' }],
      schema: z.object({
        hero: z.object({
          title: z.string().optional(),
          description: z.string(),
          icon: z.string().optional(),
          links: z.array(link).optional(),
          cards: z.array(card).optional()
        }),
        cards: z.array(card).optional()
      })
    }),
    docs: defineCollection({
      type: 'page',
      source: '1.docs/**'
    }),
    // the usage instructions of the spectrogram pages
    spectrograms: defineCollection({
      type: 'page',
      source: '2.waterfalls/spectrograms/**'
    }),
    publications: defineCollection({
      type: 'page',
      source: '3.publications.md'
    })
  }
})
