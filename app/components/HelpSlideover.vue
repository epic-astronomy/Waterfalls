<script setup lang="ts">
const { isHelpSlideoverOpen } = useDashboard()

const shortcuts = ref(false)
const query = ref('')

const links = [{
  label: 'Shortcuts',
  icon: 'i-heroicons-key',
  trailingIcon: 'i-heroicons-arrow-right-20-solid',
  onClick: () => {
    shortcuts.value = true
  }
}, {
  label: 'Documentation',
  icon: 'i-heroicons-book-open',
  to: 'https://epic-astronomy.org/docs/waterfalls',
  target: '_blank'
}, {
  label: 'GitHub repository',
  icon: 'i-simple-icons-github',
  to: 'https://github.com/epic-astronomy',
  target: '_blank'
}]

const categories = [{
  title: 'General',
  items: [
    { shortcuts: ['meta', 'K'], name: 'Command menu' },
    { shortcuts: ['?'], name: 'Help & Support' },
    { shortcuts: ['['], name: 'Hide or show the sidebar' }
  ]
}, {
  title: 'Navigation',
  items: [
    { shortcuts: ['G', 'H'], name: 'Go to Home' },
    { shortcuts: ['G', 'S'], name: 'Go to Spectrograms' }
  ]
}]

const filteredCategories = computed(() => {
  return categories.map(category => ({
    title: category.title,
    items: category.items.filter(item => {
      return item.name.search(new RegExp(query.value, 'i')) !== -1
    })
  })).filter(category => !!category.items.length)
})
</script>

<template>
  <USlideover v-model:open="isHelpSlideoverOpen" :title="shortcuts ? 'Shortcuts' : 'Help & Support'">
    <template #title>
      <div class="flex items-center gap-1.5">
        <UButton v-if="shortcuts" color="neutral" variant="ghost" size="sm" icon="i-heroicons-arrow-left-20-solid"
          @click="shortcuts = false" />
        {{ shortcuts ? 'Shortcuts' : 'Help & Support' }}
      </div>
    </template>

    <template #body>
      <div v-if="shortcuts" class="space-y-6">
        <UInput v-model="query" icon="i-heroicons-magnifying-glass" placeholder="Search..." autofocus class="w-full" />

        <div v-for="(category, index) in filteredCategories" :key="index">
          <p class="mb-3 text-sm text-highlighted font-semibold">
            {{ category.title }}
          </p>

          <div class="space-y-2">
            <div v-for="(item, i) in category.items" :key="i" class="flex items-center justify-between">
              <span class="text-sm text-muted">{{ item.name }}</span>

              <div class="flex items-center justify-end shrink-0 gap-0.5">
                <UKbd v-for="(shortcut, j) in item.shortcuts" :key="j" :value="shortcut" />
              </div>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="flex flex-col gap-y-3">
        <UButton v-for="(link, index) in links" :key="index" color="neutral" variant="outline" v-bind="link" />
      </div>
    </template>
  </USlideover>
</template>
