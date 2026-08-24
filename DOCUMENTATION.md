# Script Documentation

This document describes every Python script in the repository, what it does, and how to use it.

The project is a Flask web application ("Wiki Wall Street") backed by MongoDB, with a small set of
standalone utility scripts and a Wikipedia API wrapper module.

---

## Top-level scripts

### `appserver.py`

**Purpose:** Entry point for the Flask application.

**Usage:**

- Development server (run directly):

  ```bash
  python appserver.py
  ```

  When executed directly, it calls `create_app()` and runs the Flask development server.

- Production server (imported by Gunicorn):

  ```bash
  gunicorn appserver:gunicorn_app
  ```

  When imported, it exposes the WSGI callable `gunicorn_app` (a fully-built Flask app).

**Notes:**

- The actual app construction happens in `server/__init__.py:create_app()`.
- Requires a `.env` file in the project root (see `server/helper.py`).

---

### `gnuicorn_config.py`

**Purpose:** Gunicorn configuration file (note the filename is misspelled "gnuicorn").

**Contents:**

```python
bind = "0.0.0.0:8080"
workers = 4
threads = 8
```

**Usage (optional):**

```bash
gunicorn -c gnuicorn_config.py appserver:gunicorn_app
```

**Notes:**

- The `dockerfile` does **not** use this file; it passes Gunicorn flags directly
  (`-b 0.0.0.0:8000 --workers 8 --threads 12 --preload ...`).
- This config binds to port 8080, while the Dockerfile binds to port 8000.

---

### `get_articles.py`

**Purpose:** Builds the per-category article search lists used by the game. Given a category file
containing Wikipedia subcategory names, it fetches every article in each subcategory and writes
the results to a matching file in the search-lists directory.

**Usage:**

```bash
python get_articles.py -f server/categories/allowed/Ponds.txt
```

**How it works:**

1. Reads the `-f` file (one Wikipedia subcategory name per line).
2. For each subcategory, queries `Category:<name>` via `wikipediaapi`.
3. Writes the collected article titles to a file with the same basename, replacing
   `allowed` with `search_lists` in the path:

   ```
   server/categories/allowed/Ponds.txt  ->  server/categories/search_lists/Ponds.txt
   ```

**Requirements / caveats:**

- `-f` / `--filepath` is **required**. Running without it raises `TypeError: ... not NoneType`.
- The script sets a descriptive `user_agent` on the `wikipediaapi.Wikipedia(...)` constructor,
  per Wikimedia's User-Agent policy.
- It uses `multiprocessing.Pool(8)` to fetch categories in parallel.
- There is a hardcoded resume point:

  ```python
  start_at = "Max Verstappen"
  subcategories = subcategories[subcategories.index(start_at):]
  ```

  This line was added to resume the Formula One category build. If the input file does not
  contain the exact line `Max Verstappen`, `subcategories.index(...)` raises `ValueError`.
  Remove or adjust this line before building other category files.

**Input format** (example from `server/categories/allowed/Countries.txt`):

```
Countries in Africa
Countries in Asia
Countries in Europe
...
```

---

## Server package (`server/`)

### `server/__init__.py`

**Purpose:** Defines the Flask application factory `create_app()`.

**What it does:**

- Creates the Flask app and sets `SECRET_KEY`.
- Initializes Flask-Login with a `User` loader.
- Configures Flask-Mail, Flask-Caching, and Flask-APScheduler.
- Registers the blueprints: `auth`, `main`, `game`, `wiki`, `chat`, `admin`.
- Schedules the daily portfolio-update job unless `ENVIRONMENT == "local"`.

**Usage:** Not run directly. Imported by `appserver.py` and the route modules.

---

### `server/helper.py`

**Purpose:** Central configuration, database connections, and shared helper functions.

**What it does:**

- Loads settings from a `.env` file via `pydantic_settings.BaseSettings` (class `Settings`).
- Connects to MongoDB and exposes the users, games, transactions, players, and chats databases
  plus the relevant collections.
- Loads the category lists from `server/categories/allowed`, `server/categories/banned`, and
  `server/categories/search_lists` into dictionaries at import time.
- Defines helpers: `sanitize`, `today_wiki`, `username_is_valid`, `clear_game_caches`,
  `log_error`.

**Usage:** Imported by almost every other server module. Not run directly.

**Notes:**

- Requires a `.env` file with all fields defined in the `Settings` class, including
  `WIKI_API_USER_AGENT`, `MONGODB_CONNECTION_STRING`, mail settings, etc.
  The repository does **not** ship a `.env` (it is gitignored and dockerignored).
- `today_wiki()` returns a "quantized" UTC day boundary based on `UPDATE_HOUR_UTC`.

---

### `server/models.py`

**Purpose:** Defines the data models that wrap MongoDB documents.

**Classes:**

| Class         | MongoDB location                  | Purpose                              |
| ------------- | --------------------------------- | ------------------------------------ |
| `User`        | `active_users_coll`               | User accounts + Flask-Login methods  |
| `Game`        | `active_games_coll`               | Game instances and settings          |
| `Player`      | `players_db[game_id]`             | Player state within a game           |
| `Transaction` | `transactions_db[game_id]`        | Buy/sell transactions                |
| `Chat`        | `chats_db[game_id]`               | In-game chat messages                |

**Notable methods:**

- `User.singup(...)` (note the typo) creates a new user.
- `Game.create_game(...)`, `Game.allowed_article(...)`, `Game.delete_game(...)`.
- `Player.join_game(...)`, `Player.update_value_history(...)`,
  `Player.portfolio_value` (property).
- `Transaction.new_transaction(...)` validates and records a buy/sell.
- `Chat.send_chat(...)`, `Chat.delete_chat(...)`.

**Usage:** Imported by route modules and `server/tasks.py`. Not run directly.

---

### `server/WikiAPI.py`

**Purpose:** Python wrappers around the Wikimedia REST and MediaWiki APIs.

**Functions:**

| Function               | Underlying API                     | Returns                                  |
| ---------------------- | ---------------------------------- | ---------------------------------------- |
| `pageviews(...)`       | Pageviews `per-article`            | List of daily views for one article      |
| `projectviews(...)`    | Pageviews `aggregate`              | List of daily views for a whole project  |
| `top_articles(...)`    | Pageviews `top`                    | Top articles for a day/month             |
| `search_article(...)`  | MediaWiki OpenSearch               | Suggested articles for a query           |
| `verify_article(...)`  | (uses `search_article`)            | Whether an article exists                |
| `normalized_views(...)`| (uses `pageviews` + `projectviews`)| Pageviews normalized by project traffic  |
| `article_information(...)` | MediaWiki `query` (revisions)  | Title, pageid, short description, categories |
| `random_articles(...)` | MediaWiki `query` (random)         | Random article titles                    |

**Usage:** Imported by `server/routes/wiki.py`, `server/routes/game.py`, and `server/models.py`.
Not run directly.

**Notes:**

- Every request sends `WIKI_API_USER_AGENT` from `.env`, per Wikimedia policy.
- `normalized_views` returns `None` (and prints a warning) if the article does not exist.

---

### `server/tasks.py`

**Purpose:** Defines the scheduled background task that updates portfolio values.

**Key function:** `update_all_portfolio_vals()`

- Iterates over all active games and players.
- Calls `Player.update_value_history()` for each player (which re-fetches current pageviews).
- Adds a `"daily"` event to games whose values changed.
- Writes a log to `./server/logs/portfolio_updates/<timestamp>.txt`.

**Usage:** Not run directly in production. It is scheduled in `server/__init__.py` as an
APScheduler cron job at `UPDATE_HOUR_UTC:01` (after a cache clear at `:00`). It can also be
invoked manually:

```bash
python -c "from server.tasks import update_all_portfolio_vals; update_all_portfolio_vals()"
```

---

## Route modules (`server/routes/`)

Each route module defines a Flask `Blueprint` that is registered in `create_app()`.
They are not run directly.

### `server/routes/main.py` — Blueprint `main`

**Purpose:** Public pages and basic profile routes.

| Route                      | Description                              |
| -------------------------- | ---------------------------------------- |
| `GET /`                    | Home / index page                        |
| `GET /help`                | Help page                                |
| `GET /categories`          | Lists allowed/banned categories          |
| `GET /invite/<game_id>`    | Invite page (with social preview)        |
| `GET /invite`              | Legacy fallback (`?game_id=`)            |
| `GET /profile/<name>`      | Public user profile page                 |
| `GET /api/get_users_games/<name>` | JSON list of a user's game IDs    |

---

### `server/routes/auth.py` — Blueprint `auth`

**Purpose:** Authentication (login, signup, logout).

| Route                | Description                          |
| -------------------- | ------------------------------------ |
| `GET/POST /login`    | Login form and handler               |
| `GET/POST /signup`   | Signup form and handler              |
| `GET /logout`        | Logs the current user out            |

---

### `server/routes/game.py` — Blueprint `game`

**Purpose:** Core game routes — creating/joining games, transactions, leaderboards, play info.

| Route                                          | Description                                  |
| ---------------------------------------------- | -------------------------------------------- |
| `GET /play`                                    | Legacy fallback (`?game_id=`)                |
| `GET /play/<game_id>`                          | Main play page                               |
| `POST /api/create_game`                        | Create a game                                |
| `POST /api/change_settings`                    | Change game settings (owner only)            |
| `POST /api/join_game`                          | Join a game                                  |
| `POST /api/new_transaction`                    | Buy/sell an article                          |
| `GET /api/allowed_article/<game_id>/<article>` | Check if an article is allowed               |
| `GET /api/get_joined_games`                    | List current user's games                    |
| `GET /api/get_public_games`                    | List public games                            |
| `GET /api/get_play_info/<game_id>`             | Full play-page payload (game, player, random articles) |
| `GET /api/leaderboard/<game_id>`               | Leaderboard                                  |
| `GET /api/get_invite_info/<game_id>`           | Invite info                                  |
| `GET /api/get_profile_game/<game_id>/<user_name>` | Public profile game info                   |
| `POST /api/add_event/<game_id>/<event_name>`   | Add a game event                             |
| `POST /api/check_event/<game_id>/<event_name>` | Mark an event as seen by the player          |

---

### `server/routes/wiki.py` — Blueprint `wiki`

**Purpose:** Wikipedia-related JSON endpoints (search, prices, trending, etc.).

| Route                                     | Description                                        |
| ----------------------------------------- | -------------------------------------------------- |
| `GET /api/search_article/<game_id>/<query>` | Search articles (uses search lists then API)     |
| `GET /api/article_price/<article>/<timespan>` | Normalized pageview history for graphing        |
| `GET /api/article_information/<article>`  | Title, pageid, short description, categories      |
| `GET /api/trending_articles`              | Wikipedia's top articles with 7-day view data     |
| `GET /api/random_articles`                | Random articles (`?project=&n_articles=`)         |

**Notes:**

- `timespan` for `article_price` accepts `week`, `month`, `year`, `all`; defaults to `month`.
- Several endpoints use Flask-Caching (`@cache.cached`).

---

### `server/routes/chat.py` — Blueprint `chat`

**Purpose:** In-game chat.

| Route                         | Description                       |
| ----------------------------- | --------------------------------- |
| `GET /api/see_chat/<game_id>` | Fetch latest 100 chat messages    |
| `POST /api/send_chat`         | Send a message (`game_id`, `message`) |
| `DELETE /api/delete_chat`     | Delete own message (`chat_id`, `game_id`) |

---

### `server/routes/admin.py` — Blueprint `admin`

**Purpose:** Account management (password reset) and game administration (leave/kick/delete).

| Route                      | Description                              |
| -------------------------- | ---------------------------------------- |
| `GET /account`             | Account page                             |
| `POST /api/change_password` | Change password (requires old password) |
| `GET /forgot_password`     | Forgot-password form                     |
| `POST /api/forgot_password` | Email a password-reset link            |
| `GET /reset_password`      | Reset-password form (`?token=`)          |
| `POST /api/reset_password` | Set new password from reset token        |
| `POST /api/leave_game`     | Leave a game                             |
| `POST /api/kick_player`    | Kick a player (owner only)               |
| `POST /api/delete_game`    | Delete a game (owner only)               |

---

### `server/routes/profile.py` — Blueprint `profile`

**Purpose:** Stub/placeholder. Defines an empty `profile` blueprint and is **not** registered in
`create_app()` (registration is commented out).

---

## Running the whole application

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Create a `.env` file in the project root with all variables from `Settings` in
   `server/helper.py` (MongoDB connection string, Flask secret key, mail settings,
   `WIKI_API_USER_AGENT`, etc.).

3. Run locally:

   ```bash
   python appserver.py
   ```

   Or via Gunicorn:

   ```bash
   gunicorn -c gnuicorn_config.py appserver:gunicorn_app
   ```

4. Build the article search lists (optional, only if adding new categories):

   ```bash
   python get_articles.py -f server/categories/allowed/<Category>.txt
   ```
