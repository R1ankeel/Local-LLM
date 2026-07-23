<template>
  <section ref="scrollContainer" class="message-list" @scroll="handleScroll">
    <div v-if="showEmptyState" class="empty-state">
      <p class="empty-kicker">Ready for the first message</p>
      <h2>This chat is empty for now</h2>
      <p>
        Pick a mode, write a message, and send it. The response from Ollama arrives as a stream
        and is saved in the current chat.
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
  if (role === 'assistant') return 'Assistant'
  if (role === 'system') return 'System'
  return 'You'
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
