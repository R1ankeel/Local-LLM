import { computed, ref } from 'vue'
import { deleteJson, getJson, patchJson, postJson } from '../api/http.js'
import { toUserErrorMessage } from '../utils/errors.js'

const profiles = ref([])
const status = ref('idle')
const error = ref('')

function sortProfiles(items) {
  return [...items].sort((left, right) => {
    if (left.is_default !== right.is_default) {
      return left.is_default ? -1 : 1
    }

    return left.name.localeCompare(right.name)
  })
}

function upsertProfile(profile) {
  const next = profiles.value.filter((item) => item.id !== profile.id)
  next.push(profile)
  profiles.value = sortProfiles(next)
}

function resetProfiles() {
  profiles.value = []
  status.value = 'idle'
  error.value = ''
}

async function refreshProfiles() {
  status.value = 'loading'
  error.value = ''

  try {
    profiles.value = sortProfiles(await getJson('/profiles'))
    status.value = 'ready'
    return profiles.value
  } catch (err) {
    profiles.value = []
    status.value = 'error'
    error.value = toUserErrorMessage(err)
    throw err
  }
}

async function createProfile(payload) {
  const profile = await postJson('/profiles', payload)
  upsertProfile(profile)
  return profile
}

async function updateProfile(profileId, payload) {
  const profile = await patchJson(`/profiles/${profileId}`, payload)
  upsertProfile(profile)
  return profile
}

async function deleteProfile(profileId) {
  await deleteJson(`/profiles/${profileId}`)
  profiles.value = profiles.value.filter((profile) => profile.id !== profileId)
}

const defaultProfile = computed(() => profiles.value.find((profile) => profile.is_default) || null)

const profileOptions = computed(() =>
  profiles.value.map((profile) => ({
    id: profile.id,
    label: profile.name,
    description: profile.description,
    is_default: profile.is_default,
  })),
)

function findProfile(profileId) {
  return profiles.value.find((profile) => profile.id === profileId) || null
}

export function useProfiles() {
  return {
    createProfile,
    defaultProfile,
    deleteProfile,
    error,
    findProfile,
    profiles,
    profileOptions,
    refreshProfiles,
    resetProfiles,
    status,
    updateProfile,
  }
}
