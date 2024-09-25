<script setup lang="ts">
const hanko = useHanko()
var loggedIn = ref(false)
var emailId = ref('')
const route = useRoute()

async function initUser() {
  console.log('testing', hanko.session)
  if (hanko!.session.isValid()) {
    loggedIn.value = true
    const { data: user } = await useAsyncData('user',
      async () => {
        return hanko.user.getCurrent()
      })
    console.log(user.value.email.split('@')[0], loggedIn.value)
    emailId = user.value.email.split('@')[0]
  }
  return 'success'
}

await useAsyncData(initUser)


const userDropdownItems = [[{
  label: "Profile",
  to: "/profile",
  icon: "i-material-symbols-account-circle"
}, {
  label: "Logout",
  click: logout,
  icon: "i-material-symbols-logout"
}]]

function login(){
  navigateTo({path: '/login',query:{redirect: route.path}})
}

function logout() {
  hanko!.user.logout()
  loggedIn.value = false
  emailId.value = ''
}
</script>
<template>
  <hanko-events @onSessionCreated="initUser()"></hanko-events>
  <UButton v-if="!loggedIn" label="Sign in/Sign up" icon="i-heroicons-arrow-right-20-solid" trailing @click="login"
    class="hidden lg:flex" />
  <UDropdown v-if="loggedIn" :items="userDropdownItems" mode="hover" :popper="{ placement: 'bottom-start' }">
    <UButton color="white" :label="emailId" trailing-icon="i-heroicons-chevron-down-20-solid" />
  </UDropdown>
</template>