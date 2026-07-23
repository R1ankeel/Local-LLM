<template>
  <div class="auth-page">
    <section class="auth-card">
      <p class="brand-kicker">Local network</p>
      <h1 class="auth-title">Opening chat</h1>
      <p class="auth-copy">{{ statusText }}</p>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useChats } from '../composables/useChats.js'

const router = useRouter()
const { chats, createChat, refreshChats } = useChats()

const statusText = computed(() => {
  if (chats.value.length === 0) {
    return 'Creating your first local chat...'
  }

  return 'Opening your most recent chat...'
})

onMounted(async () => {
  try {
    await refreshChats()
  } catch {
    return
  }

  if (chats.value.length > 0) {
    await router.replace({ name: 'chat', params: { chatId: chats.value[0].id } })
    return
  }

  const chat = await createChat()
  await router.replace({ name: 'chat', params: { chatId: chat.id } })
})
</script>
