<template>
  <header class="app-header">
    <div class="brand-block">
      <p class="brand-kicker">Local network</p>
      <h1 class="brand-title">Local AI Chat</h1>
    </div>

    <div class="header-metrics">
      <div v-if="currentUser" class="metric-card">
        <span class="metric-label">User</span>
        <strong class="metric-value">{{ currentUser.username }}</strong>
      </div>
      <div class="metric-card">
        <span class="metric-label">Model</span>
        <strong class="metric-value">{{ modelName }}</strong>
      </div>
      <div class="metric-card">
        <span class="metric-label">Ollama</span>
        <strong class="metric-value">{{ ollamaStatus }}</strong>
      </div>
      <button v-if="currentUser" class="header-button" type="button" @click="$emit('logout')">
        Sign out
      </button>
    </div>
  </header>
</template>

<script setup>
defineProps({
  currentUser: {
    type: Object,
    default: null,
  },
  modelName: {
    type: String,
    default: 'Unknown',
  },
  ollamaStatus: {
    type: String,
    default: 'Unknown',
  },
})

defineEmits(['logout'])
</script>
