<template>
  <MainLayout
    :current-user="currentUser"
    :model-name="modelName"
    :ollama-status="ollamaStatus"
    @logout="handleLogout"
  >
    <section class="workspace-shell">
      <div
        v-if="isSidebarOpen"
        class="chat-sidebar-backdrop"
        aria-hidden="true"
        @click="closeSidebar"
      ></div>

      <aside class="chat-sidebar" :class="{ open: isSidebarOpen }">
        <div class="sidebar-topline">
          <div>
            <p class="brand-kicker">Chats</p>
            <h2 class="sidebar-title">Your threads</h2>
          </div>
          <div class="sidebar-actions">
            <button class="header-button sidebar-action mobile-sidebar-toggle" type="button" @click="toggleSidebar">
              {{ isSidebarOpen ? 'Close' : 'Chats' }}
            </button>
            <button class="header-button sidebar-action" type="button" @click="handleNewChat">
              New chat
            </button>
          </div>
        </div>

        <p v-if="chatsError" class="stream-error" role="alert">{{ chatsError }}</p>

        <div class="chat-list" role="list" aria-label="Chat list">
          <button
            v-for="chat in chats"
            :key="chat.id"
            type="button"
            class="chat-list-item"
            :class="{ active: chat.id === activeChatId }"
            @click="openChat(chat.id)"
          >
            <span class="chat-list-title">{{ chat.title }}</span>
            <span class="chat-list-meta">{{ formatChatDate(chat.updated_at) }}</span>
            <span class="chat-list-delete" @click.stop="removeChat(chat.id)">Delete</span>
          </button>
        </div>
      </aside>

      <section class="chat-shell">
        <div class="chat-topline">
          <div>
            <p class="brand-kicker">Current chat</p>
            <h2 class="chat-title">{{ currentChatTitle }}</h2>
          </div>
          <div class="chat-actions">
            <button class="header-button mobile-sidebar-toggle" type="button" @click="toggleSidebar">
              Chats
            </button>
            <p v-if="currentChat" class="chat-meta-inline">#{{ currentChat.id }}</p>
            <p v-if="currentChat" class="chat-meta-inline">Model: {{ modelName }}</p>
          </div>
        </div>

        <p v-if="modelNotice" class="stream-error" role="alert">{{ modelNotice }}</p>

        <MessageList :messages="currentMessages" />

        <p v-if="streamError" class="stream-error" role="alert">{{ streamError }}</p>
        <p v-else-if="healthError" class="stream-error" role="alert">{{ healthError }}</p>
        <p v-else-if="modelsError" class="stream-error" role="alert">{{ modelsError }}</p>

        <ChatComposer
          v-model="composerText"
          v-model:mode="mode"
          :disabled="isGenerating || healthStatus === 'loading' || !currentChat"
          :is-generating="isGenerating"
          placeholder="Type a message and press Enter"
          @send="sendMessage"
          @stop="stopGeneration"
        />
      </section>
    </section>
  </MainLayout>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MainLayout from '../layouts/MainLayout.vue'
import MessageList from './MessageList.vue'
import ChatComposer from './ChatComposer.vue'
import { useHealth } from '../composables/useHealth.js'
import { useChatStream } from '../composables/useChatStream.js'
import { useAuth } from '../composables/useAuth.js'
import { useChats } from '../composables/useChats.js'
import { useModels } from '../composables/useModels.js'

const composerText = ref('')
const mode = ref('instant')
const isSidebarOpen = ref(false)

const router = useRouter()
const route = useRoute()

const { health, status: healthStatus, error: healthError, refreshHealth } = useHealth()
const { isGenerating, error: streamError, sendChat, stop } = useChatStream()
const { currentUser, logout } = useAuth()
const {
  chats,
  error: chatsError,
  currentChat,
  currentChatTitle,
  currentMessages,
  createChat,
  deleteChat,
  loadChat,
  refreshChats,
  resetChats,
} = useChats()
const {
  activeModel,
  error: modelsError,
  models,
  refreshModels,
  status: modelsStatus,
} = useModels()

const modelName = computed(() => activeModel.value || health.value?.model || 'Unknown')

const ollamaStatus = computed(() => {
  if (healthStatus.value === 'loading') return 'Checking'
  if (healthStatus.value === 'error') return 'Unavailable'
  if (!health.value) return 'Unknown'
  return health.value.ollama === 'ok' ? 'Online' : 'Unavailable'
})

const activeChatId = computed(() => Number(route.params.chatId || currentChat.value?.id || 0))

const modelNotice = computed(() => {
  if (modelsStatus.value === 'error') {
    return modelsError.value || 'Ollama is unavailable'
  }

  if (models.value.length > 0 && modelName.value && !models.value.some((model) => model.name === modelName.value)) {
    return `Active model is not installed in Ollama: ${modelName.value}`
  }

  return ''
})

function uid() {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function formatChatDate(value) {
  if (!value) {
    return ''
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return ''
  }

  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

async function openChat(chatId) {
  closeSidebar()
  if (Number(chatId) === activeChatId.value) {
    return
  }

  await router.push({ name: 'chat', params: { chatId } })
}

async function handleNewChat() {
  const chat = await createChat()
  closeSidebar()
  await router.push({ name: 'chat', params: { chatId: chat.id } })
}

async function removeChat(chatId) {
  const isActive = Number(chatId) === activeChatId.value
  await deleteChat(chatId)
  await refreshChats()

  if (isActive) {
    if (chats.value.length > 0) {
      closeSidebar()
      await router.replace({ name: 'chat', params: { chatId: chats.value[0].id } })
      return
    }

    const chat = await createChat()
    closeSidebar()
    await router.replace({ name: 'chat', params: { chatId: chat.id } })
  }
}

async function syncRouteChat() {
  const chatId = Number(route.params.chatId)
  if (!chatId) {
    await router.replace({ name: 'home' })
    return
  }

  await loadChat(chatId)
  await refreshChats()
  closeSidebar()
}

function toggleSidebar() {
  isSidebarOpen.value = !isSidebarOpen.value
}

function closeSidebar() {
  isSidebarOpen.value = false
}

async function sendMessage() {
  const text = composerText.value.trim()
  const chatId = currentChat.value?.id

  if (!text || isGenerating.value || !chatId) {
    return
  }

  const userMessage = {
    id: uid(),
    chat_id: chatId,
    role: 'user',
    content: text,
  }
  const assistantMessage = {
    id: uid(),
    chat_id: chatId,
    role: 'assistant',
    content: '',
  }

  currentMessages.value = [...currentMessages.value, userMessage, assistantMessage]
  composerText.value = ''

  const result = await sendChat(
    {
      chat_id: chatId,
      content: text,
      mode: mode.value,
    },
    {
      onChunk(textValue) {
        assistantMessage.content = textValue
        currentMessages.value = currentMessages.value.map((message) =>
          message.id === assistantMessage.id ? { ...message, content: textValue } : message,
        )
      },
      onAbort({ started }) {
        if (!started) {
          currentMessages.value = currentMessages.value.filter(
            (message) => message.id !== assistantMessage.id,
          )
        }
      },
      onError({ started }) {
        if (!started) {
          currentMessages.value = currentMessages.value.filter(
            (message) => message.id !== assistantMessage.id,
          )
        }
      },
    },
  )

  if (currentChat.value?.id === chatId) {
    await loadChat(chatId)
    await refreshChats()
  }

  return result
}

function stopGeneration() {
  stop()
}

async function handleLogout() {
  stop()
  resetChats()
  await logout()
  await router.push({ name: 'login' })
}

watch(
  () => route.params.chatId,
  async (chatId) => {
    if (!chatId) {
      return
    }

    try {
      await syncRouteChat()
    } catch {
      await router.replace({ name: 'home' })
    }
  },
  { immediate: true },
)

onMounted(() => {
  refreshHealth()
  refreshModels().catch(() => {})
  refreshChats().catch(() => {})
  closeSidebar()
})

onBeforeUnmount(() => {
  stop()
})
</script>
