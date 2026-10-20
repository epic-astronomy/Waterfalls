export default defineAppConfig({
  ui: {
    colors: {
      primary: 'green',
      secondary: 'violet',
      success: 'green',
      info: 'sky',
      warning: 'amber',
      error: 'red',
      notice: 'orange',
      neutral: 'gray'
    },
    button: {
      slots: { base: 'rounded-md' }
    },
    card: {
      slots: { root: 'rounded-md' }
    }
  }
})
