<template>
  <section ref="scrollContainer" class="message-list" @scroll="handleScroll">
    <div v-if="showEmptyState" class="empty-state">
      <p class="empty-kicker">Готово к первому сообщению</p>
      <h2>Пока здесь пусто</h2>
      <p>
        Выберите режим, напишите сообщение и отправьте его. Ответ от Ollama приходит потоком и
        сохраняется в текущем чате.
      </p>
    </div>

    <div v-else class="messages">
      <article
        v-for="message in messages"
        :key="message.id"
        class="message"
        :class="`message-${message.role}`"
      >
        <p class="message-role">{{ roleLabel(message.role) }}</p>
        <p class="message-content">{{ message.content }}</p>
        <div v-if="message.sources?.length" class="message-sources">
          <p class="message-sources-title">Sources</p>
          <ol class="message-sources-list">
            <li v-for="source in message.sources" :key="source.id" class="message-source">
              <a class="message-source-link" :href="source.url" target="_blank" rel="noopener noreferrer">
                [{{ source.position }}] {{ source.title }}
              </a>
              <p v-if="source.snippet" class="message-source-snippet">{{ source.snippet }}</p>
            </li>
          </ol>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'

const props = defineProps({
  messages: {
    type: Array,
    required: true,
  },
})

const scrollContainer = ref(null)
const stickToBottom = ref(true)

const showEmptyState = computed(() => props.messages.length === 0)

function roleLabel(role) {
  if (role === 'assistant') return 'Ассистент'
  if (role === 'system') return 'Система'
  return 'Вы'
}

function scrollToBottom(force = false) {
  if (!scrollContainer.value || (!stickToBottom.value && !force)) {
    return
  }

  scrollContainer.value.scrollTop = scrollContainer.value.scrollHeight
}

function handleScroll() {
  if (!scrollContainer.value) {
    return
  }

  const { scrollTop, scrollHeight, clientHeight } = scrollContainer.value
  stickToBottom.value = scrollHeight - scrollTop - clientHeight < 80
}

watch(
  () => props.messages.map((message) => `${message.id}:${message.content}`).join('|'),
  async () => {
    await nextTick()
    scrollToBottom()
  },
)

onMounted(() => {
  scrollToBottom(true)
})
</script>
