import { createSharedComposable } from '@vueuse/core'

const _useDashboard = () => {
  const route = useRoute()
  const router = useRouter()
  const isHelpSlideoverOpen = ref(false)
  const isNotificationsSlideoverOpen = ref(false)
  // the sidebar hidden on wide screens to give the page its width; remembered in the browser
  const isSidebarHidden = useState('sidebar-hidden', () => false)
  const toggleSidebar = () => {
    isSidebarHidden.value = !isSidebarHidden.value
    try { localStorage.setItem('waterfalls-sidebar-hidden', isSidebarHidden.value ? '1' : '0') } catch { }
  }
  onNuxtReady(() => {
    try { isSidebarHidden.value = localStorage.getItem('waterfalls-sidebar-hidden') == '1' } catch { }
  })

  defineShortcuts({
    'g-h': () => router.push('/'),
    'g-p': () => router.push('/presto'),
    'g-s': () => router.push('/spectrograms'),
    '?': () => isHelpSlideoverOpen.value = true,
    '[': () => toggleSidebar(),
    n: () => isNotificationsSlideoverOpen.value = true
  })

  watch(() => route.fullPath, () => {
    isHelpSlideoverOpen.value = false
    isNotificationsSlideoverOpen.value = false
  })

  return {
    isHelpSlideoverOpen,
    isNotificationsSlideoverOpen,
    isSidebarHidden,
    toggleSidebar
  }
}

export const useDashboard = createSharedComposable(_useDashboard)