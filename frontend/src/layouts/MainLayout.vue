<template>
  <div class="page-shell">
    <AppHeader
      :current-user="currentUser"
      :model-name="modelName"
      :ollama-status="ollamaStatus"
      @logout="$emit('logout')"
    />
    <main class="page-main">
      <slot />
    </main>
  </div>
</template>

<script setup>
import AppHeader from '../components/AppHeader.vue'

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
