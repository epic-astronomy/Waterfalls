<script setup lang="ts">
// A pulsar's name on the all-sky monitor page; the Crab pulsar is a crab
import { CRAB_DATA_URL, hasIcon, pulsarTitle } from '~/lib/pulsars'
const props = defineProps<{ name: string, alias?: string | null, size?: number }>()
const title = computed(() => pulsarTitle(props.name, props.alias ?? (props.name == 'B0531+21' ? 'Crab' : null)))
</script>

<template>
  <img v-if="hasIcon(name)" :src="CRAB_DATA_URL" :alt="title" :title="title"
    :style="{ width: (size ?? 22) + 'px', height: (size ?? 22) + 'px' }" class="inline-block align-middle">
  <span v-else class="font-mono" :title="title">{{ name }}</span>
</template>
