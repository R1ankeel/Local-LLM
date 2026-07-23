from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from app.clients.ollama import OllamaClient


class ActiveModelBusyError(Exception):
    pass


class ActiveModelSwitchInProgressError(Exception):
    pass


class ModelManager:
    def __init__(self, client: OllamaClient, active_model: str) -> None:
        self._client = client
        self._active_model = active_model
        self._state_lock = asyncio.Lock()
        self._state_condition = asyncio.Condition()
        self._switching = False
        self._active_generations = 0

    @property
    def active_model(self) -> str:
        return self._active_model

    async def get_active_model(self) -> str:
        async with self._state_lock:
            return self._active_model

    @asynccontextmanager
    async def generation(self):
        async with self._state_condition:
            while self._switching:
                await self._state_condition.wait()
            self._active_generations += 1

        try:
            yield await self.get_active_model()
        finally:
            async with self._state_condition:
                self._active_generations = max(0, self._active_generations - 1)
                self._state_condition.notify_all()

    async def switch_active_model(self, next_model: str) -> str:
        async with self._state_condition:
            if self._switching:
                raise ActiveModelSwitchInProgressError("Model switch already in progress")
            if self._active_generations > 0:
                raise ActiveModelBusyError("Cannot switch active model while generation is running")
            self._switching = True

        try:
            current_model = await self.get_active_model()
            if current_model == next_model:
                return current_model

            await self._client.switch_active_model(current_model, next_model)
            async with self._state_lock:
                self._active_model = next_model
            return next_model
        finally:
            async with self._state_condition:
                self._switching = False
                self._state_condition.notify_all()
