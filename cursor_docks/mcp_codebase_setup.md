## Cognee MCP + Codebase: полная настройка

Этот файл описывает, как использовать Cognee MCP‑сервер для работы с кодовой базой (в т.ч. `helpfull_mcp/cognee_test`) в режиме **API‑mode**, с максимально возможным набором тулзов и понятными ограничениями.

---

### 1. Запуск бэкенда и MCP

1. Перейти в корень проекта:

   ```bash
   cd /Users/a.sudakov/Desktop/code/my_projects/helpfull_mcp/cognee_vk
   ```

2. Убедиться, что в `.env` заданы ключи для LLM/эмбеддингов (минимум `LLM_API_KEY` или совместимый провайдер).

3. Запустить стек с API и MCP (и Ollama/Redis/etc по необходимости):

   ```bash
   docker compose --profile mcp up --build
   ```

   Важные моменты из `docker-compose.yml`:

   - сервис `cognee` (API):
     - порты: `8000:8000`
     - том: `./cognee:/app/cognee`
   - сервис `cognee-mcp` (MCP, SSE):
     - порты: `8001:8000` (в контейнере MCP слушает 8000, снаружи — 8001)
     - тома:
       - `.env:/app/.env`
       - `./cognee:/app/cognee`
     - переменные окружения:
       - `TRANSPORT_MODE=sse`
       - `API_URL=http://host.docker.internal:8000`

   В логах `cognee-mcp` после старта должно быть:

   - `API mode enabled: http://host.docker.internal:8000`
   - `Running MCP server with SSE transport on 0.0.0.0:8000`
   - `Uvicorn running on http://0.0.0.0:8000`

   А в логах `cognee` — стандартный запуск FastAPI + успешный `/health`.

---

### 2. Настройка MCP‑клиента (Cursor / IDE)

#### 2.1 Cursor (`~/.cursor/mcp.json`)

Пример блока конфигурации:

```json
{
  "mcpServers": {
    "cognee": {
      "type": "sse",
      "url": "http://localhost:8001/sse",
      "disabled": false,
      "timeout": 60
    }
  }
}
```

Ключевой момент — **порт 8001**, а не 8000:

- контейнер MCP внутри слушает `0.0.0.0:8000`
- наружу он проброшен как `localhost:8001`

После изменения файла перезапустить Cursor, чтобы он заново установил SSE‑подключение.

#### 2.2 Проверка SSE‑соединения вручную

Опционально можно проверить SSE напрямую:

```bash
curl -v http://localhost:8001/sse
```

Ожидается:

- `HTTP/1.1 200 OK`
- заголовок `Content-Type: text/event-stream`
- “висящее” соединение (идут пустые строки / события).

---

### 3. Какие MCP‑тулзы работают в API‑mode

MCP‑сервер (`cognee-mcp/src/server.py`) использует `CogneeClient` в двух режимах:

- **API‑mode** (через HTTP к FastAPI — то, что настроено здесь)
- **direct‑mode** (прямые вызовы Python‑функций `cognee`, без API)

В текущей конфигурации (`API_URL=http://host.docker.internal:8000`) включён **API‑mode**.

В этом режиме:

- **Работают и полезны для кода:**
  - `cognify` — прогоняет пайплайн поверх уже добавленных данных (`/api/v1/cognify`).
  - `cognee_add_developer_rules` — собирает rule‑файлы (AGENTS, CLAUDE, .cursorrules и т.п.) и кладёт их в nodeset `developer_rules`.
  - `search` — поддерживает режимы:
    - `GRAPH_COMPLETION`
    - `RAG_COMPLETION`
    - `CODE`
    - `CHUNKS`
    - `SUMMARIES`
    - `CYPHER`
    - `FEELING_LUCKY`
  - `list_data` / `delete` / `prune` — управление датасетами и данными.
  - `save_interaction` — логирование запрос–ответ.

- **Ограничены в API‑mode (по замыслу ядра Cognee):**
  - `cognify_status` / `codify_status`:
    - в `CogneeClient.get_pipeline_status` при `use_api=True` жёстко выбрасывается `NotImplementedError("Pipeline status is not available via API")`;
    - MCP‑тулзы возвращают текст `❌ Pipeline status is not available in API mode`.
  - `codify`:
    - если `cognee_client.use_api` истина, тул сразу возвращает:

      ```text
      ❌ Codify operation is not available in API mode. Please use direct mode for code graph pipeline.
      ```

    - для полноценного code‑graph сейчас нужен direct‑mode (или расширение HTTP‑API на стороне Cognee).

---

### 4. Работа с локальной кодовой базой (`cognee_test/test_data`)

Цель: сделать так, чтобы MCP‑агент мог:

- читать файлы из `helpfull_mcp/cognee_test/test_data`;
- отправлять их в память (`add` + `cognify`);
- навигировать по коду через `search` в режимах `CODE` / `GRAPH_COMPLETION`.

#### 4.1 Как агенту “скормить” код

Стратегия:

1. **Собираем содержимое файлов** из `helpfull_mcp/cognee_test/test_data` на стороне агента:
   - например, объединяем содержимое `api_sample.py`, `code.py`, `docker_guide.md`, `config.json`, `sample.txt` в один большой текст с заголовками вида:

     ```text
     Файл api_sample.py:

     <код файла>

     Файл code.py:

     <код файла>
     ```

2. Вызываем MCP‑тул `cognify` с аргументами:

   - `data`: эта большая текстовая “сборка” кода;
   - `instruction_type`: для кода — обычно `nl2code` (вопросы естественным языком → код);
   - опционально `custom_prompt` — если нужно переопределить стандартные промпты.

Логика на стороне MCP такова:

- MCP‑тул `cognify` в итоге вызывает:
  - `cognee_client.add(...)` → HTTP POST `/api/v1/add`;
  - затем `cognee_client.cognify(...)` → HTTP POST `/api/v1/cognify`.

Таким образом, данные из файлов попадают в основной Cognee‑граф.

#### 4.2 Навигация по коду через `search`

После того как пайплайн отработал, можно навигировать по коду через MCP‑тул `search` с различными режимами:

- **По коду (структурно/семантически):**

  ```json
  {
    "search_query": "где описана функция, которая вызывает внешний API?",
    "search_type": "CODE",
    "instruction_type": "nl2code"
  }
  ```

- **Высокоуровневые вопросы по коду:**

  ```json
  {
    "search_query": "объясни архитектуру модуля api_sample.py",
    "search_type": "GRAPH_COMPLETION",
    "instruction_type": "nl2code"
  }
  ```

- **Поиск конкретных фрагментов:**

  ```json
  {
    "search_query": "config.json",
    "search_type": "CHUNKS",
    "instruction_type": "qa"
  }
  ```

Ответы MCP возвращаются как `TextContent` с JSON/текстом; IDE‑агент может уже отрендерить и подсветить ссылки на файлы/строки.

---

### 5. Особенности и текущие ограничения API‑mode

- **Нет статусов пайплайнов по HTTP**:
  - `cognify_status` / `codify_status` в API‑mode всегда возвращают сообщение об отсутствии поддержки.
  - Это связано с тем, что FastAPI‑сервер не публикует соответствующие эндпоинты; статус считается внутренней библиотечной функцией.

- **`codify` в API‑mode выключён умышленно**:
  - API‑сервер имеет маршруты `/api/v1/code-pipeline/index` и `/api/v1/code-pipeline/retrieve`, но:
    - они предполагают доступ к файловой системе внутри контейнера (путь к репо),
    - MCP не знает, как правильно сопоставить локальные пути IDE с путями внутри Docker.
  - Поэтому `codify` сейчас безопасно отвечает “не доступно в API‑режиме”.

- **Реальное “живое” дерево кода**:
  - Для полного code‑graph‑режима (включая `codify_status`) нужен либо:
    - direct‑mode MCP (без `API_URL`, в одном Python‑окружении с кодовой базой),
    - либо расширение HTTP‑API и аккуратное монтирование всей рабочей директории в контейнеры.

---

### 6. Рекомендуемый рабочий сценарий для IDE‑агента

- **1. Инициализация / очистка:**
  - MCP‑тул `prune()` при необходимости — очистить память (опасно, стирает всё).

- **2. Добавление и когнификация кода:**
  - Агент собирает/обновляет представление о файлах (например, `cognee_test/test_data`).
  - Для каждого значимого изменения:
    - отправляет свежий “снапшот” через `cognify(data=..., instruction_type="nl2code")`.

- **3. Навигация и ответы:**
  - Для локальной навигации по коду:
    - `search(search_query=..., search_type="CODE" | "CHUNKS", instruction_type="nl2code")`.
  - Для “умных” объяснений/обзоров:
    - `search(search_query=..., search_type="GRAPH_COMPLETION", instruction_type="nl2code")`.

- **4. Управление данными:**
  - `list_data()` — посмотреть существующие датасеты/объекты.
  - `delete(data_id=..., dataset_id=..., mode="soft" | "hard")` — точечно удалять устаревшие данные.

Этот сценарий даёт **реактивную навигацию по кодовой базе** поверх Cognee в API‑режиме, с учётом того, что IDE‑агент сам решает, какие файлы/диффы и когда “скармливать” MCP‑серверу.


