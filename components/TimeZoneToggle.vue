<script setup lang="ts">
// Shows times in UTC or in the viewer's time zone, remembered per browser
const tz = useTimeZone()
// the zone is the browser's, so it is named only once mounted
const localName = ref('')
onMounted(() => {
  tz.restore()
  localName.value = new Intl.DateTimeFormat(undefined, { timeZoneName: 'short' }).formatToParts(new Date())
    .find(p => p.type == 'timeZoneName')?.value ?? ''
})
</script>

<template>
  <UButtonGroup size="xs">
    <UButton label="UTC" :color="tz.local.value ? 'gray' : 'primary'" :variant="tz.local.value ? 'ghost' : 'solid'"
      @click="tz.setMode('utc')" />
    <UButton :label="localName ? `Local (${localName})` : 'Local'" :color="tz.local.value ? 'primary' : 'gray'"
      :variant="tz.local.value ? 'solid' : 'ghost'" @click="tz.setMode('local')" />
  </UButtonGroup>
</template>
