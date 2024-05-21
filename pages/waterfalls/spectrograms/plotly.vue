<template>
  <!-- <SpectrogramPlotly/> -->
  <SpectrogramDisplay :specgm-query="query"></SpectrogramDisplay>
    <!-- <svg
  viewBox="0 0 0 0" class="hidden"
  xmlns="http://www.w3.org/2000/svg"
  xmlns:xlink="http://www.w3.org/1999/xlink">
  <defs>
    <linearGradient id="myGradient" gradientTransform="rotate(90)">
      <stop offset="5%" stop-color="gold" />
      <stop offset="95%" stop-color="red" />
    </linearGradient>
  </defs>

   using my linear gradient 
   <circle cx="5" cy="5" r="4" fill="url('#myGradient')" />
</svg>
<svg>
    <use xlink:href="#myDot" fill="url(#myGradient)" class="hidden"/>
</svg>
<svg style="height: 0; width: 0;" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <linearGradient id="linear-gradient" x1="0.133" y1="0.008" x2="0.949" y2="1.101" gradientUnits="objectBoundingBox">
        <stop offset="0.042" stop-color="#21dbaa"/>
        <stop offset="0.358" stop-color="#00b4ef"/>
        <stop offset="0.433" stop-color="#01a7ec"/>
        <stop offset="0.568" stop-color="#0487e4"/>
        <stop offset="0.68" stop-color="#0768dd"/>
        <stop offset="0.965" stop-color="#5f1ae5"/>
      </linearGradient>
    </defs>
</svg>

<svg>
    <use xlink:href="#myDot" fill="url(#linear-gradient)" />
</svg>
<svg viewBox="0 0 80 20" xmlns="http://www.w3.org/2000/svg">
  <symbol id="myDot" width="100" height="100" viewBox="0 0 20 20">
    <circle cx="1" cy="1" r="10" fill="url(#linear-gradient)"/>
  </symbol>
</svg> -->
</template>

<script setup lang="ts">
import type { SpecgmQuery } from '~/types'; 

var query: SpecgmQuery = {
  start_time: '2024-03-31T06:16:43.000Z',
        end_time: '2024-03-31T06:18:21.000Z',
        session_id: '3ef24a6a-ef26-11ee-a893-b3f4a2d91dda',
        source_name: 'PSR B1133+16',
        pixel_positions: '(0,0)',
        n_chan:128,
        n_pols:4,
        chan_bw_hz:25000,
        start_chan: 1656
  // start_time: String,
  // end_time: String,
  // source_name: String,
  // session_id: String,
  // pixel_positions: String,
  // n_chan: number,
  // n_pols: number,
  // chan_bw_hz: number,
  // start_chan: number,
}

</script>