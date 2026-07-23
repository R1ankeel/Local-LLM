import { computed, ref } from 'vue'
import { deleteJson, getJson, patchJson, postJson } from '../api/http.js'
import { toUserErrorMessage } from '../utils/errors.js'

const chats = ref([])
const currentChat = ref(null)
const currentMessages = ref([])
const status = ref('idle')
const error = ref('')

function sortChats(items) {
  return [...items].sort((left, right) => {
    const leftTime = new Date(left.updated_at || left.created_at || 0).getTime()
    const rightTime = new Date(right.updated_at || right.created_at || 0).getTime()
    return rightTime - leftTime
  })
}

function upsertChatSummary(summary) {
  const next = chats.value.filter((chat) => chat.id !== summary.id)
  next.push(summary)
  chats.value = sortChats(next)
}

function clearCurrentChat() {
  currentChat.value = null
  currentMessages.value = []
}

function resetChats() {
  chats.value = []
  clearCurrentChat()
  status.value = 'idle'
  error.value = ''
}

async function refreshChats() {
  status.value = 'loading'
  error.value = ''

  try {
    chats.value = sortChats(await getJson('/chats'))
    status.value = 'ready'
    return chats.value
  } catch (err) {
    chats.value = []
    status.value = 'error'
    error.value = toUserErrorMessage(err)
    throw err
  }
}

async function createChat(payload = {}) {
  const chat = await postJson('/chats', payload)
  upsertChatSummary(chat)
  currentChat.value = chat
  currentMessages.value = []
  return chat
}

async function updateChatProfile(chatId, profileId) {
  const chat = await patchJson(`/chats/${chatId}`, {
    profile_id: profileId,
  })
  upsertChatSummary(chat)

  if (currentChat.value?.id === chatId) {
    currentChat.value = chat
  }

  return chat
}

async function updateChatContextMessageLimit(chatId, contextMessageLimit) {
  const chat = await patchJson(`/chats/${chatId}`, {
    context_message_limit: contextMessageLimit,
  })
  upsertChatSummary(chat)

  if (currentChat.value?.id === chatId) {
    currentChat.value = chat
  }

  return chat
}

async function loadChat(chatId) {
  status.value = 'loading'
  error.value = ''

  try {
    const chat = await getJson(`/chats/${chatId}`)
    currentChat.value = chat
    currentMessages.value = chat.messages || []
    upsertChatSummary(chat)
    status.value = 'ready'
    return chat
  } catch (err) {
    clearCurrentChat()
    status.value = 'error'
    error.value = toUserErrorMessage(err)
    throw err
  }
}

async function deleteChat(chatId) {
  await deleteJson(`/chats/${chatId}`)
  chats.value = chats.value.filter((chat) => chat.id !== chatId)

  if (currentChat.value?.id === chatId) {
    clearCurrentChat()
  }
}

function setCurrentMessages(messages) {
  currentMessages.value = messages
}

const currentChatTitle = computed(() => currentChat.value?.title || 'Новый чат')

export function useChats() {
  return {
    chats,
    clearCurrentChat,
    createChat,
    currentChat,
    currentChatTitle,
    currentMessages,
    deleteChat,
    error,
    loadChat,
    updateChatProfile,
    updateChatContextMessageLimit,
    refreshChats,
    resetChats,
    setCurrentMessages,
    status,
  }
}
