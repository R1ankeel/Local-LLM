const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api'

function buildUrl(path) {
  return `${API_BASE_URL}${path}`
}

async function parseError(response) {
  try {
    const payload = await response.json()
    if (payload && typeof payload.detail === 'string') {
      return payload.detail
    }
  } catch {
    // Fall through to a generic error message.
  }

  return `Request failed with status ${response.status}`
}

export async function requestJson(path, options = {}) {
  const response = await fetch(buildUrl(path), {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    credentials: 'include',
  })

  if (!response.ok) {
    const error = new Error(await parseError(response))
    error.status = response.status
    throw error
  }

  if (response.status === 204) {
    return null
  }

  return response.json()
}

export function getJson(path, options = {}) {
  return requestJson(path, {
    ...options,
    method: 'GET',
  })
}

export function postJson(path, body, options = {}) {
  return requestJson(path, {
    ...options,
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function deleteJson(path, options = {}) {
  return requestJson(path, {
    ...options,
    method: 'DELETE',
  })
}

export function patchJson(path, body, options = {}) {
  return requestJson(path, {
    ...options,
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function postStream(path, body, options = {}) {
  return fetch(buildUrl(path), {
    ...options,
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    body: JSON.stringify(body),
    credentials: 'include',
  })
}
