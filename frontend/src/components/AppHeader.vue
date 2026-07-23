<template>
  <header class="app-header">
    <div class="brand-block">
      <p class="brand-kicker">Локальная сеть</p>
      <h1 class="brand-title">Локальный чат с ИИ</h1>
    </div>

    <div class="header-metrics">
      <div v-if="currentUser" class="metric-card">
        <span class="metric-label">Пользователь</span>
        <strong class="metric-value">{{ currentUser.username }}</strong>
      </div>
      <div class="metric-card">
        <span class="metric-label">Модель</span>
        <strong class="metric-value">{{ modelName }}</strong>
      </div>
      <div class="metric-card">
        <span class="metric-label">Ollama</span>
        <strong class="metric-value">{{ ollamaStatus }}</strong>
      </div>
      <button v-if="currentUser" class="header-button" type="button" @click="$emit('logout')">
        Выйти
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
    default: 'Неизвестно',
  },
  ollamaStatus: {
    type: String,
    default: 'Неизвестно',
  },
})

defineEmits(['logout'])
</script>
