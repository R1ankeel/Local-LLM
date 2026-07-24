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
            <p class="brand-kicker">Чаты</p>
            <h2 class="sidebar-title">Ваши чаты</h2>
          </div>
          <div class="sidebar-actions">
            <button class="header-button sidebar-action mobile-sidebar-toggle" type="button" @click="toggleSidebar">
              {{ isSidebarOpen ? 'Закрыть' : 'Чаты' }}
            </button>
            <button class="header-button sidebar-action" type="button" @click="handleNewChat">
              Новый чат
            </button>
          </div>
        </div>

        <label class="profile-selector">
          <span>Профиль для нового чата</span>
          <select v-model="newChatProfileId" class="model-selector">
            <option :value="null">Профиль по умолчанию</option>
            <option v-for="profile in profiles" :key="profile.id" :value="profile.id">
              {{ profile.name }}{{ profile.is_default ? ' (по умолчанию)' : '' }}
            </option>
          </select>
        </label>

        <p v-if="chatsError" class="stream-error" role="alert">{{ chatsError }}</p>
        <p v-if="profilesError" class="stream-error" role="alert">{{ profilesError }}</p>

        <div class="chat-list" role="list" aria-label="Список чатов">
          <button
            v-for="chat in chats"
            :key="chat.id"
            type="button"
            class="chat-list-item"
            :class="{ active: chat.id === activeChatId }"
            @click="openChat(chat.id)"
          >
            <span class="chat-list-title">{{ chat.title }}</span>
            <span class="chat-list-meta">{{ chat.profile?.name || 'Профиль по умолчанию' }}</span>
            <span class="chat-list-meta">{{ formatChatDate(chat.updated_at) }}</span>
            <span class="chat-list-delete" @click.stop="removeChat(chat.id)">Удалить</span>
          </button>
        </div>

        <section class="profile-panel">
          <div class="sidebar-topline">
            <div>
              <p class="brand-kicker">Профили</p>
              <h2 class="sidebar-title">Профили поведения</h2>
            </div>
            <button class="header-button sidebar-action" type="button" @click="startNewProfile">
              Создать профиль
            </button>
          </div>

          <div class="profile-list">
            <article
              v-for="profile in profiles"
              :key="profile.id"
              class="profile-card"
              :class="{ active: profile.id === editingProfileId }"
            >
              <div class="profile-card-main" @click="selectProfile(profile)">
                <div class="profile-card-head">
                  <strong class="profile-card-title">{{ profile.name }}</strong>
                  <span v-if="profile.is_default" class="profile-badge">По умолчанию</span>
                </div>
                <p class="profile-card-description">{{ profile.description || 'Описание отсутствует' }}</p>
              </div>

              <div class="profile-card-actions">
                <button
                  v-if="!profile.is_default"
                  class="link-button"
                  type="button"
                  @click="makeDefault(profile)"
                >
                  Назначить по умолчанию
                </button>
                <button class="link-button danger" type="button" @click="removeProfile(profile)">
                  Удалить
                </button>
              </div>
            </article>
          </div>

          <form class="profile-form" @submit.prevent="saveProfile">
            <div class="profile-form-head">
              <div>
                <p class="brand-kicker">Редактор</p>
                <h3>{{ profileFormTitle }}</h3>
              </div>
              <p>{{ editingProfileId ? 'Изменения применятся к следующим ответам.' : 'Создайте профиль, который можно использовать снова.' }}</p>
            </div>

            <label class="auth-field">
              <span>Название</span>
              <input v-model="profileForm.name" type="text" maxlength="120" placeholder="Полезный помощник" />
            </label>

            <label class="auth-field">
              <span>Описание</span>
              <input
                v-model="profileForm.description"
                type="text"
                maxlength="240"
                placeholder="Короткое описание"
              />
            </label>

            <label class="auth-field">
              <span>Инструкции</span>
              <textarea
                v-model="profileForm.instructions"
                class="profile-textarea"
                rows="8"
                maxlength="8000"
                placeholder="Опишите тон, правила и стиль."
              ></textarea>
            </label>

            <label v-if="!editingProfileId" class="profile-default-toggle">
              <input v-model="profileForm.is_default" type="checkbox" />
              <span>Сделать профилем по умолчанию</span>
            </label>

            <p class="profile-note">Изменения применятся к следующим ответам.</p>

            <p v-if="profileActionError" class="stream-error" role="alert">{{ profileActionError }}</p>

            <div class="profile-form-actions">
              <button v-if="editingProfileId" class="header-button" type="button" @click="startNewProfile">
                Отмена
              </button>
              <button class="send-button" type="submit" :disabled="profileSaving">
                {{ profileSaving ? 'Сохранение...' : editingProfileId ? 'Сохранить профиль' : 'Создать профиль' }}
              </button>
            </div>
          </form>
        </section>

        <MemoryPanel :chat-id="currentChat?.id ?? null" />
      </aside>

      <section class="chat-shell">
        <div class="chat-topline">
          <div>
            <p class="brand-kicker">Текущий чат</p>
            <h2 class="chat-title">{{ currentChatTitle }}</h2>
            <p v-if="currentChat" class="chat-meta-inline">Профиль: {{ currentProfileLabel }}</p>
            <p v-if="currentProfileDescription" class="chat-meta-inline">{{ currentProfileDescription }}</p>
          </div>
          <div class="chat-actions">
            <button class="header-button mobile-sidebar-toggle" type="button" @click="toggleSidebar">Чаты</button>
            <p v-if="currentChat" class="chat-meta-inline">#{{ currentChat.id }}</p>
            <p v-if="currentChat" class="chat-meta-inline">Модель: {{ modelName }}</p>
            <label v-if="currentChat" class="profile-selector-inline">
              <span>Выберите профиль</span>
              <select
                :value="currentChatProfileId"
                class="model-selector"
                :disabled="isGenerating"
                @change="handleCurrentProfileChange"
              >
                <option :value="null">Профиль по умолчанию</option>
                <option v-for="profile in profiles" :key="profile.id" :value="profile.id">
                  {{ profile.name }}{{ profile.is_default ? ' (по умолчанию)' : '' }}
                </option>
              </select>
            </label>

            <label v-if="currentChat" class="profile-selector-inline context-selector">
              <span>Глубина контекста</span>
              <input
                v-model="currentChatContextMessageLimit"
                class="model-selector context-limit-input"
                type="number"
                min="10"
                max="100"
                step="1"
                :disabled="isGenerating"
                @change="handleCurrentContextLimitChange"
              />
              <span class="selector-help">Количество последних сообщений, передаваемых модели.</span>
            </label>
          </div>
        </div>

        <p v-if="chatSettingsError" class="stream-error" role="alert">{{ chatSettingsError }}</p>
        <p v-if="modelNotice" class="stream-error" role="alert">{{ modelNotice }}</p>

        <MessageList :messages="currentMessages" />

        <p v-if="streamError" class="stream-error" role="alert">{{ streamError }}</p>
        <p v-else-if="healthError" class="stream-error" role="alert">{{ healthError }}</p>
        <p v-else-if="modelsError" class="stream-error" role="alert">{{ modelsError }}</p>

        <ChatComposer
          v-model="composerText"
          v-model:mode="mode"
          v-model:web-search-mode="webSearchMode"
          v-model:web-search-provider="webSearchProvider"
          :disabled="isGenerating || healthStatus === 'loading' || !currentChat"
          :is-generating="isGenerating"
          placeholder="Введите сообщение и нажмите Enter"
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
import MemoryPanel from './MemoryPanel.vue'
import { useHealth } from '../composables/useHealth.js'
import { useChatStream } from '../composables/useChatStream.js'
import { useAuth } from '../composables/useAuth.js'
import { useChats } from '../composables/useChats.js'
import { useModels } from '../composables/useModels.js'
import { useProfiles } from '../composables/useProfiles.js'

function blankProfileForm() {
  return {
    name: '',
    description: '',
    instructions: '',
    is_default: false,
  }
}

const composerText = ref('')
const mode = ref('instant')
const webSearchMode = ref('off')
const webSearchProvider = ref('duckduckgo')
const syncingWebSearchMode = ref(false)
const syncingWebSearchProvider = ref(false)
const isSidebarOpen = ref(false)
const newChatProfileId = ref(null)
const currentChatProfileId = ref(null)
const currentChatContextMessageLimit = ref('')
const editingProfileId = ref(null)
const profileForm = ref(blankProfileForm())
const profileActionError = ref('')
const chatSettingsError = ref('')
const profileSaving = ref(false)

const router = useRouter()
const route = useRoute()

const { health, status: healthStatus, error: healthError, refreshHealth } = useHealth()
const { isGenerating, error: streamError, sendChat, stop } = useChatStream()
const { currentUser, logout, updateWebSearchMode, updateWebSearchProvider } = useAuth()
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
  updateChatContextMessageLimit,
  updateChatProfile,
} = useChats()
const {
  error: modelsError,
  models,
  refreshModels,
  status: modelsStatus,
  activeModel,
} = useModels()
const {
  profiles,
  error: profilesError,
  refreshProfiles,
  resetProfiles,
  createProfile,
  updateProfile,
  deleteProfile,
} = useProfiles()

const modelName = computed(() => activeModel.value || health.value?.model || 'Неизвестно')

const ollamaStatus = computed(() => {
  if (healthStatus.value === 'loading') return 'Проверяем'
  if (healthStatus.value === 'error') return 'Недоступна'
  if (!health.value) return 'Неизвестно'
  return health.value.ollama === 'ok' ? 'В сети' : 'Недоступна'
})

const activeChatId = computed(() => Number(route.params.chatId || currentChat.value?.id || 0))

const modelNotice = computed(() => {
  if (modelsStatus.value === 'error') {
    return modelsError.value || 'Ollama недоступна.'
  }

  if (models.value.length > 0 && modelName.value && !models.value.some((model) => model.name === modelName.value)) {
    return `Активная модель не найдена в Ollama: ${modelName.value}`
  }

  return ''
})

const currentProfileLabel = computed(() => {
  if (!currentChat.value) {
    return 'Профиль по умолчанию'
  }

  const profileId = currentChatProfileId.value
  const profile = profiles.value.find((item) => item.id === profileId)
  return profile?.name || currentChat.value.profile?.name || 'Профиль по умолчанию'
})

const currentProfileDescription = computed(() => {
  if (!currentChat.value) {
    return ''
  }

  const profileId = currentChatProfileId.value
  const profile = profiles.value.find((item) => item.id === profileId)
  return profile?.description || currentChat.value.profile?.description || ''
})

const profileFormTitle = computed(() => (editingProfileId.value ? 'Редактирование профиля' : 'Создание профиля'))

function uid() {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function normalizeProfileId(value) {
  if (value === '' || value === null || value === 'null') {
    return null
  }

  const parsed = Number(value)
  return Number.isNaN(parsed) ? null : parsed
}

function normalizeContextMessageLimit(value) {
  if (value === '' || value === null || value === undefined) {
    return null
  }

  const parsed = Number(value)
  if (!Number.isInteger(parsed)) {
    return null
  }

  return parsed
}

function formatChatDate(value) {
  if (!value) {
    return ''
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return ''
  }

  return date.toLocaleString('ru-RU', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function startNewProfile() {
  editingProfileId.value = null
  profileForm.value = blankProfileForm()
  profileActionError.value = ''
}

function selectProfile(profile) {
  editingProfileId.value = profile.id
  profileForm.value = {
    name: profile.name || '',
    description: profile.description || '',
    instructions: profile.instructions || '',
    is_default: !!profile.is_default,
  }
  profileActionError.value = ''
}

async function refreshCurrentChat() {
  if (!currentChat.value?.id) {
    return
  }

  await loadChat(currentChat.value.id)
  await refreshChats()
}

async function openChat(chatId) {
  closeSidebar()
  if (Number(chatId) === activeChatId.value) {
    return
  }

  await router.push({ name: 'chat', params: { chatId } })
}

async function handleNewChat() {
  const chat = await createChat({
    profile_id: normalizeProfileId(newChatProfileId.value),
  })
  closeSidebar()
  await router.push({ name: 'chat', params: { chatId: chat.id } })
}

async function removeChat(chatId) {
  const chat = chats.value.find((item) => item.id === chatId)
  if (!window.confirm(`Удалить чат «${chat?.title || 'Новый чат'}»?`)) {
    return
  }

  const isActive = Number(chatId) === activeChatId.value
  await deleteChat(chatId)
  await refreshChats()

  if (isActive) {
    if (chats.value.length > 0) {
      closeSidebar()
      await router.replace({ name: 'chat', params: { chatId: chats.value[0].id } })
      return
    }

    const nextChat = await createChat({
      profile_id: normalizeProfileId(newChatProfileId.value),
    })
    closeSidebar()
    await router.replace({ name: 'chat', params: { chatId: nextChat.id } })
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

async function handleCurrentProfileChange(event) {
  if (!currentChat.value?.id || isGenerating.value) {
    return
  }

  const value = normalizeProfileId(event.target.value)
  currentChatProfileId.value = value

  try {
    await updateChatProfile(currentChat.value.id, value)
    await refreshCurrentChat()
  } catch (err) {
    currentChatProfileId.value = currentChat.value?.profile_id ?? null
    profileActionError.value = err instanceof Error ? err.message : 'Не удалось обновить профиль чата.'
  }
}

async function handleCurrentContextLimitChange() {
  if (!currentChat.value?.id || isGenerating.value) {
    return
  }

  const limit = normalizeContextMessageLimit(currentChatContextMessageLimit.value)
  if (limit === null || limit < 10 || limit > 100) {
    chatSettingsError.value = 'Введите число от 10 до 100.'
    currentChatContextMessageLimit.value = String(currentChat.value?.context_message_limit ?? 40)
    return
  }

  chatSettingsError.value = ''

  try {
    const updated = await updateChatContextMessageLimit(currentChat.value.id, limit)
    currentChatContextMessageLimit.value = String(updated.context_message_limit)
  } catch (err) {
    currentChatContextMessageLimit.value = String(currentChat.value?.context_message_limit ?? 40)
    chatSettingsError.value = err instanceof Error ? err.message : 'Не удалось обновить глубину контекста.'
  }
}

async function saveProfile() {
  if (profileSaving.value) {
    return
  }

  const name = profileForm.value.name.trim()
  const description = profileForm.value.description.trim()
  const instructions = profileForm.value.instructions.trim()

  if (!name) {
    profileActionError.value = 'Название профиля не может быть пустым.'
    return
  }

  if (!instructions) {
    profileActionError.value = 'Инструкции профиля не могут быть пустыми.'
    return
  }

  profileSaving.value = true
  profileActionError.value = ''

  try {
    if (editingProfileId.value) {
      await updateProfile(editingProfileId.value, {
        name,
        description,
        instructions,
      })
    } else {
      const profile = await createProfile({
        name,
        description,
        instructions,
        is_default: profileForm.value.is_default,
      })
      newChatProfileId.value = profile.id
    }

    await refreshProfiles()
    await refreshCurrentChat()

    if (editingProfileId.value) {
      const updated = profiles.value.find((profile) => profile.id === editingProfileId.value)
      if (updated) {
        selectProfile(updated)
      }
    } else {
      startNewProfile()
    }
  } catch (err) {
    profileActionError.value = err instanceof Error ? err.message : 'Не удалось сохранить профиль.'
  } finally {
    profileSaving.value = false
  }
}

async function makeDefault(profile) {
  profileActionError.value = ''

  try {
    await updateProfile(profile.id, {
      is_default: true,
    })
    newChatProfileId.value = profile.id
    await refreshProfiles()
    await refreshCurrentChat()
  } catch (err) {
    profileActionError.value = err instanceof Error ? err.message : 'Не удалось назначить профиль по умолчанию.'
  }
}

async function removeProfile(profile) {
  profileActionError.value = ''

  if (!window.confirm(`Удалить профиль «${profile.name}»?`)) {
    return
  }

  try {
    await deleteProfile(profile.id)
    await refreshProfiles()
    await refreshCurrentChat()

    if (editingProfileId.value === profile.id) {
      startNewProfile()
    }

    if (newChatProfileId.value === profile.id) {
      newChatProfileId.value = null
    }
  } catch (err) {
    profileActionError.value = err instanceof Error ? err.message : 'Не удалось удалить профиль.'
  }
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
      web_search_mode: webSearchMode.value,
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
    await refreshCurrentChat()
  }

  return result
}

function stopGeneration() {
  stop()
}

async function handleLogout() {
  stop()
  resetChats()
  resetProfiles()
  startNewProfile()
  newChatProfileId.value = null
  currentChatProfileId.value = null
  currentChatContextMessageLimit.value = ''
  webSearchProvider.value = 'duckduckgo'
  composerText.value = ''
  chatSettingsError.value = ''
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

watch(
  () => currentChat.value?.profile_id,
  (profileId) => {
    currentChatProfileId.value = profileId ?? null
  },
  { immediate: true },
)

watch(
  () => currentChat.value?.id,
  () => {
    chatSettingsError.value = ''
  },
  { immediate: true },
)

watch(
  () => currentChat.value?.context_message_limit,
  (limit) => {
    currentChatContextMessageLimit.value = limit !== undefined && limit !== null ? String(limit) : ''
  },
  { immediate: true },
)

watch(
  () => currentUser.value?.web_search_mode,
  (mode) => {
    const nextMode = mode || 'off'
    if (webSearchMode.value === nextMode) {
      return
    }

    syncingWebSearchMode.value = true
    webSearchMode.value = nextMode
    queueMicrotask(() => {
      syncingWebSearchMode.value = false
    })
  },
  { immediate: true },
)

watch(
  () => currentUser.value?.web_search_provider,
  (provider) => {
    const nextProvider = provider || 'duckduckgo'
    if (webSearchProvider.value === nextProvider) {
      return
    }

    syncingWebSearchProvider.value = true
    webSearchProvider.value = nextProvider
    queueMicrotask(() => {
      syncingWebSearchProvider.value = false
    })
  },
  { immediate: true },
)

watch(webSearchMode, async (mode, previousMode) => {
  if (syncingWebSearchMode.value || !currentUser.value || mode === previousMode) {
    return
  }

  if (mode === currentUser.value.web_search_mode) {
    return
  }

  try {
    await updateWebSearchMode(mode)
  } catch (err) {
    syncingWebSearchMode.value = true
    webSearchMode.value = currentUser.value?.web_search_mode || 'off'
    queueMicrotask(() => {
      syncingWebSearchMode.value = false
    })
    chatSettingsError.value = err instanceof Error ? err.message : 'Не удалось сохранить режим поиска.'
  }
})

watch(webSearchProvider, async (provider, previousProvider) => {
  if (syncingWebSearchProvider.value || !currentUser.value || provider === previousProvider) {
    return
  }

  if (provider === currentUser.value.web_search_provider) {
    return
  }

  try {
    await updateWebSearchProvider(provider)
  } catch (err) {
    syncingWebSearchProvider.value = true
    webSearchProvider.value = currentUser.value?.web_search_provider || 'duckduckgo'
    queueMicrotask(() => {
      syncingWebSearchProvider.value = false
    })
    chatSettingsError.value = err instanceof Error ? err.message : 'Не удалось сохранить источник поиска.'
  }
})

watch(
  profiles,
  () => {
    if (newChatProfileId.value !== null && !profiles.value.some((profile) => profile.id === newChatProfileId.value)) {
      newChatProfileId.value = null
    }

    if (
      currentChatProfileId.value !== null &&
      !profiles.value.some((profile) => profile.id === currentChatProfileId.value)
    ) {
      currentChatProfileId.value = currentChat.value?.profile_id ?? null
    }
  },
  { immediate: true, deep: true },
)

onMounted(() => {
  refreshHealth()
  refreshModels().catch(() => {})
  refreshChats().catch(() => {})
  refreshProfiles().catch(() => {})
  closeSidebar()
})

onBeforeUnmount(() => {
  stop()
})
</script>
