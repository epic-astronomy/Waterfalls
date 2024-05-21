export default defineAppConfig({
  ui: {
    notifications: {
      // Show toasts at the top right of the screen
      position: 'top-0 bottom-auto'
    },
    primary: 'green',
    gray: 'cool',
    button: {
      rounded: 'rounded-md',
      default: {
        size: 'md'
      }
    },
    input: {
      default: {
        size: 'md'
      }
    },
    card: {
      rounded: 'rounded-md'
    },
    footer: {
      top: {
        wrapper: 'border-t border-gray-200 dark:border-gray-800',
        container: 'py-8 lg:py-16'
      },
      bottom: {
        wrapper: 'border-t border-gray-200 dark:border-gray-800'
      }
    },
    landing: {
      hero: {
        wrapper: 'py-20 sm:py-20 md:py-20 relative'
      }
    }
  }
})