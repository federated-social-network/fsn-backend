<h1 align="center">🗄️ Heliix Database Schema</h1>

<p align="center">
  Detailed overview of the PostgreSQL database tables and relationships powering the Heliix backend.
</p>

---

## Overview

The database uses **PostgreSQL**, managed by **SQLAlchemy ORM** and **Alembic** for migrations. 
All tables use `uuid` strings as primary keys for optimal distributed performance and collision avoidance.

## Tables

### `users`
Stores user profile information, authentication hashes, and ActivityPub federation keys.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | `String` | `PRIMARY KEY` | UUID string |
| `username` | `String` | `UNIQUE, NOT NULL` | Login username |
| `password_hash` | `String` | `NOT NULL` | Argon2 hashed password |
| `email` | `String` | `UNIQUE` | Email for login and resets |
| `avatar_url` | `String` | | Remote URL to avatar image in Supabase |
| `public_key` | `Text` | | RSA public key for ActivityPub HTTP signatures |
| `private_key` | `Text` | | RSA private key (stored securely, used for signing outgoing requests) |
| `bio` | `String(500)` | | Short user biography |
| `display_name` | `String(100)` | | Friendly name shown in the UI |

### `posts`
Stores all posts created by local users, as well as fetched federated posts from remote users.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | `String` | `PRIMARY KEY` | Post UUID (or ActivityPub ID for remote posts) |
| `content` | `Text` | `NOT NULL` | Post body content |
| `author` | `String` | `NOT NULL` | Original author's username |
| `image_url` | `String` | | URL to attached image |
| `user_id` | `String` | `FOREIGN KEY(users.id), CASCADE` | Nullable for remote posts without a local placeholder |
| `origin_instance` | `String` | `NOT NULL` | The name or domain of the instance where the post originated |
| `is_remote` | `Boolean` | `DEFAULT FALSE` | True if the post came from a remote server (e.g., Mastodon) |
| `like_count` | `Integer` | `DEFAULT 0` | Denormalized count of likes |
| `visibility` | `String` | `NOT NULL, DEFAULT 'public'` | Post visibility ("public" or "private") |
| `comment_count` | `Integer` | `DEFAULT 0` | Denormalized count of comments |
| `created_at` | `DateTime` | `NOT NULL, server_default=now()` | Timestamp of creation |

### `activities`
Logs incoming and outgoing ActivityPub activities for auditing, persistence, and possible retries.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | `String` | `PRIMARY KEY` | Generated UUID |
| `type` | `String` | `NOT NULL` | Activity type (Create, Delete, Follow, Accept, Undo) |
| `actor` | `String` | `NOT NULL` | Actor URI performing the activity |
| `object` | `JSON` | `NOT NULL` | Full JSON-LD Activity object payload |
| `created_at` | `DateTime` | `DEFAULT utcnow()` | Timestamp |
| `is_local` | `Boolean` | `DEFAULT TRUE` | True if the activity originated from this local instance |
| `is_delivered` | `Boolean` | `DEFAULT FALSE` | Tracks if an outgoing activity was successfully sent |

### `connections`
Manages relationships (Follows/Friends) between users, including local-to-remote federation connections.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | `String` | `PRIMARY KEY` | Generated UUID |
| `local_user_id` | `String` | `FOREIGN KEY(users.id), CASCADE, NOT NULL` | Local user initiating or receiving the connection |
| `target_local_user_id` | `String` | `FOREIGN KEY(users.id), CASCADE, NULL` | Target user, if both users are local |
| `remote_actor_url` | `String` | | Target actor's URL, if connecting to a remote user |
| `remote_inbox_url` | `String` | | Target actor's inbox URL, used to deliver activities |
| `status` | `String` | `DEFAULT 'pending'` | 'pending' or 'accepted' |
| `created_at` | `DateTime` | `DEFAULT utcnow()` | Timestamp |

### `password_resets`
Tracks password reset requests via email One-Time Passwords (OTPs).

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | `String` | `PRIMARY KEY` | Reset Token UUID |
| `user_id` | `String` | `FOREIGN KEY(users.id), CASCADE, NOT NULL` | Target account |
| `otp` | `String` | `NOT NULL` | Verification code |
| `otp_expires_at` | `DateTime` | `NOT NULL` | Expiration limit for OTP (default 10 mins) |
| `is_used` | `Boolean` | `DEFAULT FALSE` | Prevents reuse of tokens |
| `created_at` | `DateTime` | `DEFAULT utcnow()` | Creation timestamp |

### `likes`
Junction table tracking which users liked which posts.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | `String` | `PRIMARY KEY` | Generated UUID |
| `user_id` | `String` | `FOREIGN KEY(users.id), CASCADE, NOT NULL` | Liked by |
| `post_id` | `String` | `FOREIGN KEY(posts.id), CASCADE, NOT NULL` | Liked post |
| `created_at` | `DateTime` | `DEFAULT utcnow()` | Timestamp |

> **Constraint:** Unique combined key on `(user_id, post_id)` to prevent duplicate likes.

### `comments`
Stores replies to posts.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | `String` | `PRIMARY KEY` | Generated UUID |
| `content` | `Text` | `NOT NULL` | Comment body |
| `user_id` | `String` | `FOREIGN KEY(users.id), CASCADE, NOT NULL` | Author |
| `post_id` | `String` | `FOREIGN KEY(posts.id), CASCADE, NOT NULL` | Parent post |
| `created_at` | `DateTime` | `DEFAULT utcnow()` | Timestamp |

> **Constraint:** Unique combined key on `(user_id, post_id, content)` to discourage identical spam comments.

### `messages`
Stores direct, real-time chat text between users.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | `String` | `PRIMARY KEY` | Generated UUID |
| `sender_id` | `String` | `FOREIGN KEY(users.id), CASCADE, NOT NULL` | Sender |
| `receiver_id` | `String` | `FOREIGN KEY(users.id), CASCADE, NOT NULL` | Receiver |
| `content` | `Text` | `NOT NULL` | Message body |
| `is_read` | `Boolean` | `DEFAULT FALSE` | Read receipt status |
| `created_at` | `DateTime` | `DEFAULT utcnow()` | Timestamp |

> **Indices:** Indexed on `(sender_id, receiver_id)` for fast conversation history lookup.

### `notifications`
System alerts for various user interactions.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | `String` | `PRIMARY KEY` | Generated UUID |
| `recipient_id` | `String` | `FOREIGN KEY(users.id), CASCADE, NOT NULL` | Notified user |
| `actor_id` | `String` | `FOREIGN KEY(users.id), CASCADE, NOT NULL` | User triggering the alert |
| `type` | `String` | `NOT NULL` | Notification type (e.g., 'follow_request', 'like', 'comment') |
| `object_id` | `String` | | Optional reference ID (e.g., connection ID, post ID) |
| `is_read` | `Boolean` | `DEFAULT FALSE` | Seen status |
| `created_at` | `DateTime` | `DEFAULT utcnow()` | Timestamp |

> **Indices:** Indexed on `(recipient_id)` to quickly load user notification feeds.
