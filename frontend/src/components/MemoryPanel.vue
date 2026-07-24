<template>
  <section class="memory-panel">
    <div class="sidebar-topline">
      <div>
        <p class="brand-kicker">Память</p>
        <h2 class="sidebar-title">Долговременная память</h2>
      </div>
      <button class="header-button sidebar-action" type="button" @click="startCreate">
        Новая память
      </button>
    </div>

    <p class="profile-note">
      Ручные записи попадают в системный prompt, а кандидаты помогают быстро найти новые факты из текущего чата.
    </p>

    <section class="candidate-panel">
      <div class="sidebar-topline">
        <div>
          <p class="brand-kicker">Кандидаты</p>
          <h3 class="sidebar-title candidate-title">Предложения в память</h3>
        </div>
        <button
          class="header-button sidebar-action"
          type="button"
          :disabled="!chatId || candidateStatus === 'loading'"
          @click="analyzeCandidates"
        >
          {{ candidateStatus === 'loading' ? 'Анализ...' : 'Анализировать чат' }}
        </button>
      </div>

      <p class="profile-note">
        Анализ смотрит на текущий чат и предлагает только устойчивые факты, которые стоит сохранить.
      </p>

      <div v-if="candidateLoadError" class="memory-error-block">
        <p class="stream-error" role="alert">
          {{ candidateLoadError }}
        </p>
        <button
          class="header-button"
          type="button"
          :disabled="candidateStatus === 'loading'"
          @click="refreshMemoryCandidates(chatId).catch(() => {})"
        >
          Обновить кандидатов
        </button>
      </div>

      <p v-if="candidateActionError" class="stream-error" role="alert">
        {{ candidateActionError }}
      </p>

      <div v-if="!chatId" class="memory-status">
        Откройте чат, чтобы искать кандидатов в память.
      </div>

      <div v-else-if="isCandidateInitialLoading" class="memory-status">
        Загружаем кандидатов...
      </div>

      <div v-else-if="isCandidateEmpty" class="empty-state memory-empty">
        <h3>Пока нет предложений</h3>
        <p>Нажмите «Анализировать чат», чтобы найти новые факты для постоянной памяти.</p>
      </div>

      <div v-else class="memory-list">
        <article
          v-for="candidate in memoryCandidates"
          :key="candidate.id"
          class="memory-card candidate-card"
          :class="`candidate-${candidate.status}`"
        >
          <div class="memory-card-head">
            <div class="memory-card-main">
              <strong class="memory-card-title">{{ candidate.content }}</strong>
              <p class="memory-card-meta">
                {{ candidateStatusLabel(candidate.status) }}
              </p>
            </div>
            <span class="memory-badge" :class="`candidate-${candidate.status}`">
              {{ candidateStatusBadge(candidate.status) }}
            </span>
          </div>

          <div class="candidate-card-actions">
            <button
              v-if="candidate.status === 'pending'"
              class="link-button"
              type="button"
              :disabled="isCandidateBusy(candidate.id)"
              @click="acceptCandidate(candidate)"
            >
              Принять
            </button>
            <button
              v-if="candidate.status === 'pending'"
              class="link-button danger"
              type="button"
              :disabled="isCandidateBusy(candidate.id)"
              @click="rejectCandidate(candidate)"
            >
              Отклонить
            </button>
          </div>
        </article>
      </div>
    </section>

    <div v-if="loadError" class="memory-error-block">
      <p class="stream-error" role="alert">
        {{ loadError }}
      </p>
      <button class="header-button" type="button" :disabled="status === 'loading'" @click="refreshMemories().catch(() => {})">
        Обновить память
      </button>
    </div>

    <p v-if="actionError" class="stream-error" role="alert">
      {{ actionError }}
    </p>

    <form class="memory-form" @submit.prevent="submitMemory">
      <label class="auth-field">
        <span>{{ formTitle }}</span>
        <textarea
          v-model="draftContent"
          class="profile-textarea memory-textarea"
          rows="4"
          maxlength="500"
          placeholder="Например: любит короткие ответы и пьёт чай без сахара."
          :disabled="isFormSaving"
        ></textarea>
      </label>

      <p class="profile-note">
        {{ isEditing ? 'Измените запись и сохраните её снова.' : 'Добавьте явный факт, который нужно подмешивать в будущие ответы.' }}
      </p>

      <div class="memory-form-actions">
        <button
          v-if="isEditing"
          class="header-button"
          type="button"
          :disabled="isFormSaving"
          @click="cancelEdit"
        >
          Отмена
        </button>
        <button class="send-button" type="submit" :disabled="isFormSaving">
          {{ isFormSaving ? 'Сохранение...' : isEditing ? 'Сохранить память' : 'Добавить память' }}
        </button>
      </div>
    </form>

    <div v-if="isInitialLoading" class="memory-status">Загружаем память...</div>

    <div v-else-if="isEmpty" class="empty-state memory-empty">
      <h3>Память пуста</h3>
      <p>Сохраните несколько фактов вручную или примите кандидатов из анализа чата.</p>
    </div>

    <div v-else class="memory-list" role="list" aria-label="Список памяти">
      <article
        v-for="memory in memories"
        :key="memory.id"
        class="memory-card"
        :class="{ inactive: !memory.is_active, editing: memory.id === editingMemoryId }"
      >
        <div class="memory-card-head">
          <div class="memory-card-main">
            <strong class="memory-card-title">{{ memory.content }}</strong>
            <p class="memory-card-meta">
              {{ memory.is_active ? 'Активная запись' : 'Отключённая запись' }}
            </p>
          </div>
          <span class="memory-badge" :class="{ inactive: !memory.is_active }">
            {{ memory.is_active ? 'Активна' : 'Выключена' }}
          </span>
        </div>

        <p v-if="memory.id === editingMemoryId" class="memory-edit-note">
          Эта запись сейчас редактируется.
        </p>

        <div class="memory-card-actions">
          <button
            class="link-button"
            type="button"
            :disabled="isMemoryBusy(memory.id)"
            @click="toggleMemory(memory)"
          >
            {{ memory.is_active ? 'Отключить' : 'Активировать' }}
          </button>
          <button
            class="link-button"
            type="button"
            :disabled="isMemoryBusy(memory.id)"
            @click="startEdit(memory)"
          >
            Редактировать
          </button>
          <button
            class="link-button danger"
            type="button"
            :disabled="isMemoryBusy(memory.id)"
            @click="removeMemory(memory)"
          >
            Удалить
          </button>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useMemories } from '../composables/useMemories.js'
import { useMemoryCandidates } from '../composables/useMemoryCandidates.js'

const props = defineProps({
  chatId: {
    type: Number,
    default: null,
  },
})

const {
  memories,
  status,
  error,
  refreshMemories,
  createMemory,
  updateMemory,
  deleteMemory,
} = useMemories()
const {
  analyzeMemoryCandidates,
  error: candidateError,
  memoryCandidates,
  refreshMemoryCandidates,
  reviewMemoryCandidate,
  status: candidateStatus,
} = useMemoryCandidates()

const draftContent = ref('')
const editingMemoryId = ref(null)
const actionError = ref('')
const candidateActionError = ref('')
const isFormSaving = ref(false)
const busyMemoryIds = ref(new Set())
const busyCandidateIds = ref(new Set())

const isEditing = computed(() => editingMemoryId.value !== null)
const isInitialLoading = computed(() => status.value === 'loading' && memories.value.length === 0)
const isEmpty = computed(() => status.value === 'ready' && memories.value.length === 0)
const loadError = computed(() => (status.value === 'error' ? error.value : ''))
const isCandidateInitialLoading = computed(
  () => candidateStatus.value === 'loading' && memoryCandidates.value.length === 0,
)
const isCandidateEmpty = computed(
  () => candidateStatus.value === 'ready' && memoryCandidates.value.length === 0,
)
const candidateLoadError = computed(() => (candidateStatus.value === 'error' ? candidateError.value : ''))
const formTitle = computed(() => (isEditing.value ? 'Редактирование памяти' : 'Добавить память'))

function setBusy(memoryId, isBusy) {
  const next = new Set(busyMemoryIds.value)
  if (isBusy) {
    next.add(memoryId)
  } else {
    next.delete(memoryId)
  }
  busyMemoryIds.value = next
}

function setCandidateBusy(candidateId, isBusy) {
  const next = new Set(busyCandidateIds.value)
  if (isBusy) {
    next.add(candidateId)
  } else {
    next.delete(candidateId)
  }
  busyCandidateIds.value = next
}

function isMemoryBusy(memoryId) {
  return busyMemoryIds.value.has(memoryId) || (isFormSaving.value && editingMemoryId.value === memoryId)
}

function isCandidateBusy(candidateId) {
  return busyCandidateIds.value.has(candidateId)
}

function clearForm() {
  draftContent.value = ''
  editingMemoryId.value = null
  actionError.value = ''
}

function startCreate() {
  clearForm()
}

function startEdit(memory) {
  actionError.value = ''
  editingMemoryId.value = memory.id
  draftContent.value = memory.content
}

function cancelEdit() {
  clearForm()
}

function candidateStatusLabel(status) {
  if (status === 'accepted') {
    return 'Принято в память'
  }

  if (status === 'rejected') {
    return 'Отклонено'
  }

  return 'Ожидает решения'
}

function candidateStatusBadge(status) {
  if (status === 'accepted') {
    return 'Принято'
  }

  if (status === 'rejected') {
    return 'Отклонено'
  }

  return 'Новый'
}

async function submitMemory() {
  const content = draftContent.value.trim()
  if (!content) {
    actionError.value = 'Поле памяти не может быть пустым.'
    return
  }

  const targetMemoryId = editingMemoryId.value
  isFormSaving.value = true
  actionError.value = ''

  if (targetMemoryId !== null) {
    setBusy(targetMemoryId, true)
  }

  try {
    if (targetMemoryId !== null) {
      await updateMemory(targetMemoryId, { content })
      clearForm()
      return
    }

    await createMemory({ content })
    draftContent.value = ''
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : 'Не удалось сохранить память.'
  } finally {
    if (targetMemoryId !== null) {
      setBusy(targetMemoryId, false)
    }
    isFormSaving.value = false
  }
}

async function analyzeCandidates() {
  if (!props.chatId) {
    return
  }

  candidateActionError.value = ''

  try {
    await analyzeMemoryCandidates(props.chatId)
  } catch (err) {
    candidateActionError.value = err instanceof Error ? err.message : 'Не удалось проанализировать чат.'
  }
}

async function acceptCandidate(candidate) {
  if (!props.chatId || isCandidateBusy(candidate.id)) {
    return
  }

  candidateActionError.value = ''
  setCandidateBusy(candidate.id, true)

  try {
    await reviewMemoryCandidate(props.chatId, candidate.id, { status: 'accepted' })
    await refreshMemories()
    await refreshMemoryCandidates(props.chatId)
  } catch (err) {
    candidateActionError.value = err instanceof Error ? err.message : 'Не удалось принять кандидата.'
  } finally {
    setCandidateBusy(candidate.id, false)
  }
}

async function rejectCandidate(candidate) {
  if (!props.chatId || isCandidateBusy(candidate.id)) {
    return
  }

  candidateActionError.value = ''
  setCandidateBusy(candidate.id, true)

  try {
    await reviewMemoryCandidate(props.chatId, candidate.id, { status: 'rejected' })
    await refreshMemoryCandidates(props.chatId)
  } catch (err) {
    candidateActionError.value = err instanceof Error ? err.message : 'Не удалось отклонить кандидата.'
  } finally {
    setCandidateBusy(candidate.id, false)
  }
}

async function toggleMemory(memory) {
  if (isMemoryBusy(memory.id)) {
    return
  }

  actionError.value = ''
  setBusy(memory.id, true)

  try {
    await updateMemory(memory.id, {
      is_active: !memory.is_active,
    })
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : 'Не удалось изменить память.'
  } finally {
    setBusy(memory.id, false)
  }
}

async function removeMemory(memory) {
  if (isMemoryBusy(memory.id)) {
    return
  }

  actionError.value = ''

  if (!window.confirm(`Удалить запись «${memory.content}»?`)) {
    return
  }

  setBusy(memory.id, true)

  try {
    await deleteMemory(memory.id)
    if (editingMemoryId.value === memory.id) {
      clearForm()
    }
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : 'Не удалось удалить память.'
  } finally {
    setBusy(memory.id, false)
  }
}

watch(
  () => props.chatId,
  async (chatId) => {
    candidateActionError.value = ''
    if (!chatId) {
      await refreshMemoryCandidates(null)
      return
    }

    try {
      await refreshMemoryCandidates(chatId)
    } catch {
      // Ошибка уже сохранена в composable.
    }
  },
  { immediate: true },
)

onMounted(() => {
  refreshMemories().catch(() => {})
})
</script>
