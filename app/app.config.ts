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
    },
    // the heroes' height as before (UI 4 pads them up to py-40, pushing the cards down)
    pageHero: {
      slots: { container: 'py-16 sm:py-20 lg:py-20' }
    }
  }
})
