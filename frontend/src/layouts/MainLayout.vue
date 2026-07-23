<template>
  <div class="page-shell">
    <AppHeader :model-name="modelName" :ollama-status="ollamaStatus" />
    <main class="page-main">
      <slot />
    </main>
  </div>
</template>

<script setup>
import AppHeader from '../components/AppHeader.vue'

defineProps({
  modelName: {
    type: String,
    default: 'Unknown',
  },
  ollamaStatus: {
    type: String,
    default: 'Unknown',
  },
})
</script>
