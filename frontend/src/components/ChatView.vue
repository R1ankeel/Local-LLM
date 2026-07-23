<template>
  <MainLayout :model-name="modelName" :ollama-status="ollamaStatus">
    <section class="chat-shell">
      <MessageList :messages="messages" />

      <p v-if="streamError" class="stream-error" role="alert">{{ streamError }}</p>
      <p v-else-if="healthError" class="stream-error" role="alert">{{ healthError }}</p>

      <ChatComposer
        v-model="composerText"
        v-model:mode="mode"
        :disabled="isGenerating || healthStatus === 'loading'"
        :is-generating="isGenerating"
        placeholder="Введите сообщение и нажмите Enter"
        @send="sendMessage"
        @stop="stopGeneration"
      />
    </section>
  </MainLayout>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import MainLayout from '../layouts/MainLayout.vue'
import MessageList from './MessageList.vue'
import ChatComposer from './ChatComposer.vue'
import { useHealth } from '../composables/useHealth.js'
import { useChatStream } from '../composables/useChatStream.js'

const messages = ref([])
const composerText = ref('')
const mode = ref('instant')

const { health, status: healthStatus, error: healthError, refreshHealth } = useHealth()
const { isGenerating, error: streamError, sendChat, stop } = useChatStream()

const modelName = computed(() => health.value?.model || 'Unknown')
const ollamaStatus = computed(() => {
  if (healthStatus.value === 'loading') return 'Checking'
  if (healthStatus.value === 'error') return 'Unavailable'
  if (!health.value) return 'Unknown'
  return health.value.ollama === 'ok' ? 'Online' : 'Unavailable'
})

function uid() {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function appendMessage(role, content) {
  const message = {
    id: uid(),
    role,
    content,
  }

  messages.value.push(message)
  return message
}

function removeMessage(messageId) {
  messages.value = messages.value.filter((message) => message.id !== messageId)
}

async function sendMessage() {
  const text = composerText.value.trim()
  if (!text || isGenerating.value) {
    return
  }

  appendMessage('user', text)
  const assistantMessage = appendMessage('assistant', '')
  composerText.value = ''

  const requestMessages = messages.value.slice(0, -1).map((message) => ({
    role: message.role,
    content: message.content,
  }))

  await sendChat(
    {
      messages: requestMessages,
      mode: mode.value,
    },
    {
      onChunk(textValue) {
        assistantMessage.content = textValue
      },
      onAbort({ started }) {
        if (!started) {
          removeMessage(assistantMessage.id)
        }
      },
      onError({ started }) {
        if (!started) {
          removeMessage(assistantMessage.id)
        }
      },
    },
  )
}

function stopGeneration() {
  stop()
}

onMounted(() => {
  refreshHealth()
})

onBeforeUnmount(() => {
  stop()
})
</script>
