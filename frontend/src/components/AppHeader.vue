<template>
  <header class="app-header">
    <div class="brand-block">
      <p class="brand-kicker">Local network</p>
      <h1 class="brand-title">Local AI Chat</h1>
    </div>

    <div class="header-metrics">
      <div class="metric-card">
        <span class="metric-label">Model</span>
        <strong class="metric-value">{{ modelName }}</strong>
      </div>
      <div class="metric-card">
        <span class="metric-label">Ollama</span>
        <strong class="metric-value">{{ ollamaStatus }}</strong>
      </div>
    </div>
  </header>
</template>

<script setup>
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
