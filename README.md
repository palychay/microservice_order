# OrderFlow — микросервисный backend

Учебный backend для оформления и оплаты заказов: авторизация по JWT, каталог товаров, заказы, имитация оплаты и журнал событий. Сервисы взаимодействуют по HTTP, через RabbitMQ и Kafka. Весь backend запускается через Docker Compose.

Проект включает только backend-часть, без frontend и Nginx.

## Возможности

- Регистрация и вход с хешированием паролей Argon2 и выдачей JWT.
- Создание товаров и чтение каталога.
- Оформление заказа с расчётом суммы по ценам каталога.
- Сохранение названия и цены товара на момент оформления.
- Проверка JWT и владельца заказа на API Gateway.
- Имитация успешной оплаты с задержкой в четыре секунды.
- Обновление статуса заказа через событие RabbitMQ.
- Публикация событий оплаты в Kafka и сохранение в MongoDB.
- Защита журнала аналитики от повторной записи одного `event_id`.
- Swagger для каждого HTTP-сервиса.

## Архитектура

```mermaid
flowchart TD
    Client["curl / Swagger"] --> Gateway["API Gateway"]
    Gateway --> Auth["Авторизация"]
    Gateway --> Catalog["Каталог"]
    Gateway --> Orders["Заказы"]
    Orders -->|HTTP| Catalog
    Orders -->|HTTP| Payments["Оплата"]
    Payments --> Rabbit["RabbitMQ"]
    Rabbit -->|"payment.succeeded"| Orders
    Payments --> Kafka["Kafka"]
    Kafka --> Analytics["Аналитика"]
    Analytics --> Mongo["MongoDB"]
```

| Сервис | Ответственность | Хранилище |
|---|---|---|
| `api-gateway` | Публичный API, проверка JWT, проверка владельца заказа | Нет |
| `auth-service` | Пользователи, хеширование паролей, выдача JWT | PostgreSQL `auth` |
| `catalog-service` | Товары и цены | PostgreSQL `catalog` |
| `order-service` | Заказы, позиции и итоговая сумма | PostgreSQL `orders` |
| `payment-service` | Платежи и публикация результата | PostgreSQL `payments` |
| `analytic-service` | Чтение Kafka и просмотр событий | MongoDB `analytics.events` |

Каждый бизнес-сервис владеет своим хранилищем. Заказы получают информацию о товарах через HTTP, а не читают базу каталога напрямую. Межсервисные идентификаторы `user_id`, `product_id` и `order_id` не являются внешними ключами между базами.

### Сценарий оформления

1. Пользователь входит и получает JWT.
2. Шлюз проверяет токен и добавляет `user_id` к запросу создания заказа.
3. Заказы запрашивают товары у каталога, рассчитывают сумму и сохраняют заказ с позициями.
4. После фиксации заказа создаётся платёж по HTTP.
5. Оплата ждёт четыре секунды и сохраняет статус `succeeded`.
6. Одно событие с одинаковым `event_id` публикуется в RabbitMQ и Kafka.
7. Потребитель заказов получает событие RabbitMQ и устанавливает `paid`.
8. Аналитика читает Kafka, сохраняет документ в MongoDB и затем фиксирует offset.

HTTP-запрос оформления ожидает завершения имитации оплаты. Обработка сообщения RabbitMQ происходит независимо: первый ответ может содержать `created` или уже `paid`. Актуальный статус проверяется повторным GET.

## Стек

Python 3.14, FastAPI, Uvicorn, Pydantic Settings, SQLAlchemy 2, PostgreSQL 16, psycopg2, asyncpg, HTTPX, PyJWT, pwdlib/Argon2, RabbitMQ 3.13, aio-pika, Apache Kafka 4.3.1, aiokafka, MongoDB 8.0, PyMongo Async API, Docker Compose.

Каталог, авторизация и заказы используют синхронные сессии SQLAlchemy; оплата — `AsyncSession`. Для оплаты зависимость устанавливается как `SQLAlchemy[asyncio]`, включая необходимый `greenlet`.

## Структура

| Путь | Содержимое |
|---|---|
| `api-gateway/app/` | Общий HTTP-клиент, JWT-проверка, схемы и роутеры |
| `auth-service/app/` | Пользователи, безопасность, регистрация и вход |
| `catalog-service/app/` | Модель товара и API каталога |
| `order-service/app/` | Модели заказа, бизнес-логика, HTTP-клиенты и RabbitMQ consumer |
| `payment-service/app/` | Асинхронная работа с БД, платежи, события и отправители брокеров |
| `analytic-service/app/` | MongoDB, Kafka consumer и API событий |
| `infra/compose.yml` | Все приложения, базы и брокеры |
| `requirements-dev.txt` | Общий список зависимостей для локального Python-окружения |

В каждом сервисе находятся собственные `requirements.txt`, `Dockerfile` и `.dockerignore`.

## Запуск

Нужны Docker с Compose v2 и запущенный Docker Engine. На macOS можно использовать Docker Desktop. Python на компьютере нужен только для приведённых ниже команд генерации секрета, curl-проверок и необязательного запуска без контейнеров.

Все команды этого раздела выполняются из корня репозитория.

### 1. Скачать репозиторий

Подставьте адрес своей опубликованной копии:

```bash
git clone <URL_ВАШЕГО_РЕПОЗИТОРИЯ> microservice_order
cd microservice_order
```

### 2. Подготовить JWT-секрет

Compose читает файлы `auth-service/.env` и `api-gateway/.env`. Они не должны попадать в Git. Секрет и алгоритм должны совпадать у обоих сервисов.

При первом запуске новой копии выполните:

```bash
JWT_SECRET_VALUE=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
printf 'JWT_SECRET=%s\nJWT_ALGORITHM=HS256\n' "$JWT_SECRET_VALUE" > auth-service/.env
cp auth-service/.env api-gateway/.env
unset JWT_SECRET_VALUE
```

Эти команды создают или перезаписывают оба файла. В уже настроенном проекте сохраните существующий секрет: его смена делает ранее выданные токены недействительными.

Настройки подключений контейнеров заданы в `infra/compose.yml`; для Docker-запуска остальные `.env` не требуются.

### 3. Запустить инфраструктуру

```bash
docker compose -f infra/compose.yml up -d \
  auth-db catalog-db order-db payment-db rabbitmq kafka mongodb

docker compose -f infra/compose.yml ps
```

Дождитесь статуса `healthy` у баз и брокеров. Затем создайте топик:

```bash
docker compose -f infra/compose.yml exec kafka \
  /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server kafka:29092 \
  --create --if-not-exists \
  --topic payment-events \
  --partitions 1 \
  --replication-factor 1
```

### 4. Запустить приложения

```bash
docker compose -f infra/compose.yml up -d --build
docker compose -f infra/compose.yml ps
```

Первый запуск скачивает образы и устанавливает библиотеки. Проверить завершение запуска приложений можно по сообщению `Application startup complete` в логах:

```bash
docker compose -f infra/compose.yml logs --tail=100 \
  api-gateway auth-service catalog-service order-service \
  payment-service analytic-service
```

У приложения с зависимостью `service_started` Compose ожидает запуск контейнера, а не готовность его HTTP API. После старта системы дайте приложениям завершить инициализацию.

## Адреса

| Компонент | Адрес с компьютера |
|---|---|
| API Gateway / Swagger | http://localhost:8000/docs |
| Каталог / Swagger | http://localhost:8001/docs |
| Заказы / Swagger | http://localhost:8002/docs |
| Оплата / Swagger | http://localhost:8003/docs |
| Авторизация / Swagger | http://localhost:8004/docs |
| Аналитика / Swagger | http://localhost:8005/docs |
| Последние события | http://localhost:8005/events?limit=20 |
| Панель RabbitMQ | http://localhost:15672 — `orderflow` / `orderflow` |
| Kafka | `localhost:9092` |
| MongoDB | `localhost:27017` |
| PostgreSQL: каталог / заказы / оплата / авторизация | `localhost:5433` / `5434` / `5435` / `5436` |

Между контейнерами используются имена сервисов и внутренние порты: `catalog-service:8000`, `order-service:8000`, `payment-service:8000`, `auth-service:8000`, `rabbitmq:5672`, `kafka:29092`, `mongodb:27017`; PostgreSQL — порт `5432`.

## API

### Публичные маршруты шлюза

| Метод | Маршрут | JWT | Назначение |
|---|---|---|---|
| POST | `/api/auth/register` | Нет | Регистрация и выдача токена |
| POST | `/api/auth/login` | Нет | Вход и выдача токена |
| GET | `/api/auth/me` | Да | Пользователь из токена |
| GET | `/api/products` | Нет | Список товаров |
| GET | `/api/products/{product_id}` | Нет | Один товар |
| POST | `/api/orders` | Да | Создание заказа |
| GET | `/api/orders/{order_id}` | Да | Чтение собственного заказа |

Токен передаётся заголовком `Authorization: Bearer <TOKEN>`. В Swagger через кнопку **Authorize** нужно вставить только токен.

Запрос создания заказа содержит только `items`. Поля владельца и цены клиент не задаёт. При чтении чужого заказа шлюз возвращает `404`.

### Прямые маршруты сервисов

| Сервис | Маршруты |
|---|---|
| Каталог | `POST /products`, `GET /products`, `GET /products/{product_id}` |
| Авторизация | `POST /register`, `POST /login` |
| Заказы | `POST /orders`, `GET /orders`, `GET /orders/{order_id}` |
| Оплата | `POST /payments`, `GET /payments`, `GET /payments/{payment_id}` |
| Аналитика | `GET /events?limit=20` — допустимый limit от 1 до 100 |

Прямые API заказов, оплаты и аналитики не выполняют проверку JWT. Порты опубликованы для локальной разработки; проверка владельца заказа реализована на шлюзе. Создание товара через шлюз не предоставляется.

## Проверка через curl

Команды рассчитаны на Bash/Zsh и Python 3. Выполняйте их в одном терминале. Проверка создаёт пользователя, товар, заказ и платёж.

### Регистрация и токен

```bash
EMAIL="check-$(date +%s)@example.com"
PASSWORD="Test-password-123"

AUTH_RESPONSE=$(curl -fsS \
  -X POST http://localhost:8000/api/auth/register \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")

TOKEN=$(printf '%s' "$AUTH_RESPONSE" | \
  python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

curl -fsS http://localhost:8000/api/auth/me \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

Для повторного входа используйте `POST /api/auth/login` с теми же `email` и `password`.

### Товар

Суммы в этой реализации считаются целыми числами в копейках: `129000` соответствует 1290 рублям.

```bash
PRODUCT_RESPONSE=$(curl -fsS \
  -X POST http://localhost:8001/products \
  -H 'Content-Type: application/json' \
  -d '{"name":"Тестовая кружка","description":"Проверка backend","price":129000,"image":"","category":"Посуда"}')

PRODUCT_ID=$(printf '%s' "$PRODUCT_RESPONSE" | \
  python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

curl -fsS "http://localhost:8000/api/products/$PRODUCT_ID" | python3 -m json.tool
```

### Заказ и результат оплаты

```bash
ORDER_RESPONSE=$(curl -fsS \
  -X POST http://localhost:8000/api/orders \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $TOKEN" \
  -d "{\"items\":[{\"product_id\":\"$PRODUCT_ID\",\"quantity\":2}]}")

printf '%s' "$ORDER_RESPONSE" | python3 -m json.tool

ORDER_ID=$(printf '%s' "$ORDER_RESPONSE" | \
  python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

curl -fsS "http://localhost:8000/api/orders/$ORDER_ID" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

Ожидаются `total_amount: 258000` и после обработки события `status: "paid"`. Если статус ещё `created`, повторите GET через секунду.

```bash
curl -fsS http://localhost:8003/payments | python3 -m json.tool
curl -fsS 'http://localhost:8005/events?limit=5' | python3 -m json.tool
```

В платежах и событиях найдите тот же `order_id`. У платежа и события статус `succeeded`. При необходимости повторите запрос аналитики через пару секунд.

### Ожидаемые ошибки

| Проверка | Результат |
|---|---|
| Повторная регистрация email | `409` |
| Вход с неверными учётными данными допустимого формата | `401` |
| Отсутствующий или некорректный токен для защищённого маршрута | Отказ в доступе |
| Чтение чужого или отсутствующего заказа через шлюз | `404` |
| Пустой список позиций или количество `0` | `422` |
| Неположительная сумма платежа | `422` |

## События

```json
{
  "event_id": "uuid-события",
  "created_at": "2026-10-21T10:00:00+00:00",
  "payment_id": "uuid-платежа",
  "order_id": "uuid-заказа",
  "amount": 258000,
  "status": "succeeded"
}
```

**RabbitMQ:** durable direct exchange `payment.events`, routing key `payment.succeeded`, durable очередь `payment.results`, persistent-сообщения. Заказы фиксируют изменение в PostgreSQL до подтверждения сообщения. Повтор для уже оплаченного заказа не меняет его статус. По текущей настройке обработчика ошибка приводит к отклонению сообщения без возврата в очередь; отдельной очереди ошибок нет.

**Kafka:** топик `payment-events`, группа аналитики `orderflow-analytics`. При отсутствии сохранённой позиции используется `earliest`; иначе чтение продолжается с позиции группы. Автоматический commit отключён.

**MongoDB:** коллекция `analytics.events`, уникальный индекс по `event_id`. Запись выполняется через upsert с `$setOnInsert`; повтор того же события не создаёт второй документ. Offset Kafka фиксируется после успешной операции MongoDB.

## Управление системой

```bash
# Запуск и сборка изменённых образов
docker compose -f infra/compose.yml up -d --build

# Состояние
docker compose -f infra/compose.yml ps

# Логи выбранных приложений; Ctrl+C останавливает только просмотр
docker compose -f infra/compose.yml logs -f order-service payment-service analytic-service

# Перезапуск контейнера без пересборки образа
docker compose -f infra/compose.yml restart payment-service

# Остановка с сохранением контейнеров и данных
docker compose -f infra/compose.yml stop

# Удаление контейнеров и сети без удаления именованных томов
docker compose -f infra/compose.yml down
```

Изменения Python-кода применяются после пересборки соответствующего образа, например `docker compose -f infra/compose.yml up -d --build order-service`. Обычный `restart` не копирует новый код в образ. Не добавляйте `-v` к `down`, если нужно сохранить данные именованных томов.

PostgreSQL, MongoDB и Kafka используют тома. В текущем Compose для RabbitMQ отдельный постоянный том не добавлен; пересоздание его контейнера не следует считать сохранением очередей и сообщений, несмотря на durable-настройки.

## Необязательный запуск Python-сервисов на компьютере

Для разработки можно оставить базы и брокеры в Docker, а приложения запускать через общее окружение:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

Остановите контейнер приложения перед запуском локального сервера на том же порту. В каждом терминале переходите в папку нужного сервиса: это важно для импорта `app` и чтения `.env`.

Пример каталога:

```bash
cd catalog-service
source ../.venv/bin/activate
python -m uvicorn app.main:app --reload --port 8001
```

Порты остальных приложений приведены в таблице адресов. Для локального запуска используйте опубликованные адреса зависимостей (`localhost`), а не контейнерные имена. Полный набор значений по умолчанию находится в `app/config.py` каждого сервиса. Для оплаты обязательно задайте локальный адрес БД:

```dotenv
DATABASE_URL=postgresql+asyncpg://payments:payments@localhost:5435/payments
RABBITMQ_URL=amqp://orderflow:orderflow@localhost:5672/
```

Для заказов также переопределите `RABBITMQ_URL` на `orderflow:orderflow`. Локальному шлюзу нужны адреса каталога `http://localhost:8001`, заказов `http://localhost:8002`, авторизации `http://localhost:8004` и тот же JWT-секрет.

## Особенности реализации

- Это учебная имитация оплаты без подключения платёжного провайдера, списания денег и обработки отказов банка.
- Отдельных сервисов корзины и уведомлений нет. Заказ создаётся из переданного списка позиций.
- Таблицы PostgreSQL создаются при старте через `create_all()`. Миграции Alembic не добавлены; изменение моделей не обновляет существующие таблицы автоматически.
- Заказ фиксируется до вызова оплаты. Ошибка оплаты не отменяет уже сохранённый заказ.
- Запись платежа и публикации в двух брокерах не атомарны. Transactional outbox и автоматическое восстановление пропущенных публикаций не реализованы.
- Повтор HTTP-запроса оформления может создать новый заказ и платёж; отдельного ключа идемпотентности нет.
- Шлюз проверяет JWT без обращения к базе пользователей. Роль в токене фиксирована как `user`; отдельной системы ролей нет.
- В публичной схеме учётных данных шлюза удаляются пробелы по краям строк, включая пароль; прямой auth API этого не делает.
- Аналитика показывает журнал событий, без расчёта метрик. HTTP API может быть доступен раньше подключения фонового consumer к Kafka; работу consumer следует проверять по новым событиям и логам.
- Порты внутренних сервисов и простые пароли предназначены для локального запуска. Конфигурация не заявляется как готовая к публичному развёртыванию.

## Детали реализации

- Backend запускается единым `infra/compose.yml`, без frontend и Nginx.
- Добавлены проверки пустого заказа, положительного количества и суммы платежа.
- Исправлены вход с неизвестным email, обработка повторного email и поиск платежа по идентификатору.
- Добавлены HTTP-ответы для отсутствующих заказов и платежей, ошибок соседних сервисов.
- Согласованы таймауты HTTP с задержкой оплаты; для внутренних вызовов отключено использование прокси из окружения.
- Добавлены корректное асинхронное закрытие ресурсов, durable-настройки RabbitMQ и проверка отсутствующего заказа в consumer.
- Аналитика использует группу Kafka, ручной commit после MongoDB и защиту от повторов по `event_id`.
- Для локальной разработки используется общее `.venv`, а Docker-образы устанавливают зависимости каждого сервиса отдельно.