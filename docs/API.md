<h1 align="center">📡 Heliix API Reference</h1>

<p align="center">
  Complete REST API documentation for the Heliix federated social network backend.<br/>
  Interactive Swagger UI is available at <a href="https://heliix.studio/docs">heliix.studio/docs</a>.
</p>

---

## Base URL

| Environment | URL |
|---|---|
| **Production** | `https://heliix.studio` |
| **Local Dev** | `http://localhost:8000` |

---

## Authentication

All authenticated endpoints require a **Bearer token** in the `Authorization` header:

```
Authorization: Bearer <access_token>
```

Tokens are obtained via the `/auth/login` endpoint and can be refreshed using `/auth/refresh`.

| Token | Lifetime | Purpose |
|---|---|---|
| Access Token | Short-lived | API request authorization |
| Refresh Token | Long-lived | Obtain new access tokens |

---

## 🔐 Auth — `/auth`

Handles user registration, login, JWT token management, and password reset via email OTP.

### `POST /auth/register`

Register a new user account. Generates an RSA keypair for ActivityPub federation.

**Parameters (query):**

| Name | Type | Required | Description |
|---|---|---|---|
| `username` | `string` | ✅ | Alphanumeric, dashes, underscores only |
| `password` | `string` | ✅ | User password (hashed with Argon2) |
| `email` | `string` | ✅ | Unique email address |

**Responses:**

| Code | Description |
|---|---|
| `200` | `{"message": "user created"}` |
| `400` | Invalid username format |
| `409` | Username or email already exists |

---

### `POST /auth/login`

Authenticate and receive JWT access + refresh tokens.

**Parameters (query):**

| Name | Type | Required | Description |
|---|---|---|---|
| `username` | `string` | ✅ | Registered username |
| `password` | `string` | ✅ | Account password |

**Response (200):**

```json
{
  "access_token": "eyJhbGciOi...",
  "refresh_token": "eyJhbGciOi..."
}
```

| Code | Description |
|---|---|
| `401` | Invalid credentials |

---

### `POST /auth/forgot-password`

Initiate a password reset by sending a one-time password (OTP) to the user's email.

**Request Body (JSON):**

```json
{
  "email": "user@example.com"
}
```

| Code | Description |
|---|---|
| `200` | OTP sent successfully |
| `404` | Email not found |

---

### `POST /auth/verify-otp`

Verify the OTP sent to the user's email. Returns a time-limited reset token.

**Request Body (JSON):**

```json
{
  "email": "user@example.com",
  "otp": "123456"
}
```

**Response (200):**

```json
{
  "message": "OTP verified",
  "reset_token": "eyJhbGciOi..."
}
```

| Code | Description |
|---|---|
| `400` | Invalid or expired OTP |

---

### `POST /auth/reset-password`

Reset the password using a verified reset token.

**Request Body (JSON):**

```json
{
  "reset_token": "eyJhbGciOi...",
  "new_password": "newSecurePassword123"
}
```

| Code | Description |
|---|---|
| `200` | Password reset successfully |
| `400` | Invalid or expired reset token |

---

### `POST /auth/refresh`

Exchange a valid refresh token for a new access token.

**Parameters (query):**

| Name | Type | Required | Description |
|---|---|---|---|
| `refresh_token` | `string` | ✅ | Valid refresh token |

**Response (200):**

```json
{
  "access_token": "eyJhbGciOi..."
}
```

| Code | Description |
|---|---|
| `401` | Invalid or expired refresh token |

---

## 📝 Posts

Handles creating, reading, deleting posts, and managing likes and comments.

### `POST /posts`

Create a new post with text and/or an image. Images are validated for MIME type, size (≤2 MB, ≤2000×2000 px), and moderated via Google Cloud Vision SafeSearch. Posts are cached in Redis and optionally federated to remote instances.

🔒 **Requires authentication**

**Parameters (form-data):**

| Name | Type | Required | Description |
|---|---|---|---|
| `content` | `string` | ❌ | Post text content |
| `image` | `file` | ❌ | Image file (JPEG, PNG, WebP; ≤2 MB) |
| `visibility` | `string` | ❌ | `"public"` (default) or `"private"` |

> At least one of `content` or `image` must be provided.

**Responses:**

| Code | Description |
|---|---|
| `200` | Post created successfully, returns post object |
| `400` | Neither content nor image provided / unsafe image / invalid format |
| `413` | Image exceeds 2 MB or 2000×2000 px |

---

### `GET /get_posts`

Get all public posts ordered by creation date (descending).

**Response:** Array of post objects.

---

### `GET /timeline`

Get the personalized global timeline. Includes local public posts (not from the current user), enriched with like status, author details, and avatar URLs. Results are cached in Redis for performance.

🔒 **Requires authentication**

**Response:** Array of post objects with enriched metadata.

---

### `GET /timeline_connected_users`

Get posts from connected/followed users, including remote (federated) posts from users followed via ActivityPub.

🔒 **Requires authentication**

**Response:** Array of post objects from connected users.

---

### `DELETE /delete/{post_id}`

Delete a post. Only the post author can delete their own posts. If federation is enabled, sends a `Delete` activity to remote instances.

🔒 **Requires authentication**

| Parameter | Type | Location | Description |
|---|---|---|---|
| `post_id` | `string` | path | UUID of the post to delete |

| Code | Description |
|---|---|
| `200` | Post deleted |
| `403` | Not the post owner |
| `404` | Post not found |

---

### `POST /like/{post_id}`

Like a post. Increments the post's `like_count` and creates a notification for the post author.

🔒 **Requires authentication**

| Parameter | Type | Location | Description |
|---|---|---|---|
| `post_id` | `string` | path | UUID of the post to like |

| Code | Description |
|---|---|
| `200` | Post liked |
| `400` | Already liked |

---

### `DELETE /unlike/{post_id}`

Unlike a previously liked post. Decrements the post's `like_count`.

🔒 **Requires authentication**

| Parameter | Type | Location | Description |
|---|---|---|---|
| `post_id` | `string` | path | UUID of the post to unlike |

| Code | Description |
|---|---|
| `200` | Post unliked |
| `400` | Not yet liked |

---

### `POST /comments/{post_id}`

Add a comment to a post. Increments `comment_count` and creates a notification.

🔒 **Requires authentication**

| Parameter | Type | Location | Description |
|---|---|---|---|
| `post_id` | `string` | path | UUID of the post |

**Request Body (JSON):**

```json
{
  "content": "Great post!"
}
```

| Code | Description |
|---|---|
| `200` | Comment created |
| `404` | Post not found |

---

### `GET /comments/{post_id}`

Get all comments on a post, ordered by creation date (ascending). Includes author details and avatars.

| Parameter | Type | Location | Description |
|---|---|---|---|
| `post_id` | `string` | path | UUID of the post |

---

### `DELETE /comments/{comment_id}`

Delete a comment. Only the comment author can delete their own comments. Decrements `comment_count`.

🔒 **Requires authentication**

| Parameter | Type | Location | Description |
|---|---|---|---|
| `comment_id` | `string` | path | UUID of the comment |

| Code | Description |
|---|---|
| `200` | Comment deleted |
| `403` | Not the comment owner |
| `404` | Comment not found |

---

## 🤖 AI Features

Groq-powered AI assistance for composing posts.

### `POST /complete_post`

AI auto-completes a partially written post. Returns 3 different suggestions.

**Parameters (form-data):**

| Name | Type | Required | Description |
|---|---|---|---|
| `content` | `string` | ✅ | Partial post content to auto-complete |

**Response (200):**

```json
{
  "suggestions": [
    "...completed version 1...",
    "...completed version 2...",
    "...completed version 3..."
  ]
}
```

---

### `POST /eloborate_post`

AI elaborates on a short post, making it more detailed and engaging. Returns 3 variations.

**Parameters (form-data):**

| Name | Type | Required | Description |
|---|---|---|---|
| `content` | `string` | ✅ | Short post to elaborate on |

**Response (200):**

```json
{
  "suggestions": [
    "...elaborated version 1...",
    "...elaborated version 2...",
    "...elaborated version 3..."
  ]
}
```

---

## 👤 Users

User profiles, connections (follow/friend system), avatar uploads, and user search.

### `GET /get_current_user`

Get the authenticated user's profile information.

🔒 **Requires authentication**

**Response (200):**

```json
{
  "id": "uuid",
  "username": "alice",
  "email": "alice@example.com",
  "avatar_url": "https://...",
  "bio": "Hello world",
  "display_name": "Alice"
}
```

---

### `GET /get_user/{username}`

Get a user's public profile, including their post count and connection status with the current user.

🔒 **Requires authentication**

| Parameter | Type | Location | Description |
|---|---|---|---|
| `username` | `string` | path | Target username |

---

### `GET /search_users?q=`

Search for users. Supports local prefix search and remote handle lookup via WebFinger.

🔒 **Requires authentication**

| Parameter | Type | Location | Description |
|---|---|---|---|
| `q` | `string` | query | Search query (e.g., `"alice"` or `"alice@mastodon.social"`) |

**Behavior:**

- **Local search** (`alice`): Finds local users whose username starts with the query
- **Remote search** (`alice@mastodon.social`): Resolves via WebFinger and returns the remote actor profile

---

### `GET /random_users`

Get random user suggestions for the current user. Excludes already-connected users.

🔒 **Requires authentication**

---

### `POST /connect/{username}`

Send a connection (follow) request to a local user. Creates a notification for the target user.

🔒 **Requires authentication**

| Parameter | Type | Location | Description |
|---|---|---|---|
| `username` | `string` | path | Target user's username |

| Code | Description |
|---|---|
| `200` | Connection request sent |
| `400` | Cannot connect to yourself / already connected |
| `404` | User not found |

---

### `POST /connect/remote/{handle}`

Follow a remote (federated) user. Resolves the handle via WebFinger, fetches the actor profile, and sends a signed `Follow` activity.

🔒 **Requires authentication**

| Parameter | Type | Location | Description |
|---|---|---|---|
| `handle` | `string` | path | Remote handle (e.g., `alice@mastodon.social`) |

---

### `POST /connect/accept/{connection_id}`

Accept a pending connection request. If the requester is a remote actor, sends a signed `Accept` activity and fetches their existing outbox posts.

🔒 **Requires authentication**

| Parameter | Type | Location | Description |
|---|---|---|---|
| `connection_id` | `string` | path | UUID of the connection request |

---

### `GET /connections/pending`

Get all pending incoming connection requests for the current user. Includes actor display names (resolved for remote users).

🔒 **Requires authentication**

---

### `GET /connections/count`

Get the total number of accepted connections for the current user.

🔒 **Requires authentication**

---

### `GET /list_connections`

List all accepted connections with user details (username, avatar, display name).

🔒 **Requires authentication**

---

### `POST /remove_connection/{username}`

Remove a connection with a user. If the target is a remote actor, sends an `Undo(Follow)` activity.

🔒 **Requires authentication**

| Parameter | Type | Location | Description |
|---|---|---|---|
| `username` | `string` | path | Username or remote handle to disconnect from |

---

### `POST /upload_avatar`

Upload a profile avatar image. Accepts JPEG, PNG, WebP up to 2 MB. Resized to 400×400 px and stored in Supabase.

🔒 **Requires authentication**

**Parameters (form-data):**

| Name | Type | Required | Description |
|---|---|---|---|
| `file` | `file` | ✅ | Avatar image (JPEG, PNG, WebP; ≤2 MB) |

---

### `PUT /update_profile`

Update user profile fields (bio, display name, avatar).

🔒 **Requires authentication**

**Parameters (form-data):**

| Name | Type | Required | Description |
|---|---|---|---|
| `bio` | `string` | ❌ | Profile bio (max 500 chars) |
| `display_name` | `string` | ❌ | Display name (max 100 chars) |
| `image` | `file` | ❌ | New avatar image |

---

## 💬 Chat & Calls

Real-time messaging via WebSockets and WebRTC voice/video call signaling.

### `WS /ws/chat/{user_id}`

WebSocket endpoint for real-time communication. Handles three message types:

#### Chat Messages

```json
{
  "type": "chat",
  "receiver_id": "user-uuid",
  "content": "Hello!"
}
```

Messages are persisted to the database and delivered in real-time to the receiver.

#### Read Receipts

```json
{
  "type": "read_receipt",
  "sender_id": "user-uuid"
}
```

Marks all unread messages from the specified sender as read and notifies them.

#### WebRTC Signaling

Messages with `type` prefixed by `webrtc_` (e.g., `webrtc_offer`, `webrtc_answer`, `webrtc_ice_candidate`) are forwarded directly to the target user for peer-to-peer call negotiation.

```json
{
  "type": "webrtc_offer",
  "receiver_id": "user-uuid",
  "sdp": "..."
}
```

Sender info (display name, avatar, username) is automatically injected into forwarded payloads.

---

### `GET /messages/{user1}/{user2}`

Get full message history between two users, ordered chronologically.

| Parameter | Type | Location | Description |
|---|---|---|---|
| `user1` | `string` | path | First user's ID |
| `user2` | `string` | path | Second user's ID |

**Response:** Array of message objects.

---

### `GET /conversations`

Get all conversations for the current user, showing the latest message from each conversation partner.

🔒 **Requires authentication**

**Response:** Array of conversation summaries with `other_user`, `username`, `avatar_url`, `content`, and `created_at`.

---

## 🔔 Notifications

### `GET /notifications`

Get the 10 most recent notifications for the current user. Includes full actor and recipient details.

🔒 **Requires authentication**

**Notification types:** `follow_request`, `follow_accept`, `like`, `comment`, `message`

**Response (200):**

```json
[
  {
    "id": "uuid",
    "type": "follow_request",
    "object_id": "connection-uuid",
    "created_at": "2026-03-10T12:00:00",
    "is_read": false,
    "actor": {
      "id": "uuid",
      "display_name": "Bob",
      "avatar_url": "https://...",
      "username": "bob"
    },
    "recipient": {
      "id": "uuid",
      "display_name": "Alice",
      "avatar_url": "https://...",
      "username": "alice"
    }
  }
]
```

---

## 🛡️ Content Moderation

### `POST /moderate-image`

Analyze an uploaded image using Google Cloud Vision SafeSearch.

**Parameters (form-data):**

| Name | Type | Required | Description |
|---|---|---|---|
| `file` | `file` | ✅ | Image file to analyze |

**Response (200):**

```json
{
  "adult": "VERY_UNLIKELY",
  "violence": "UNLIKELY",
  "racy": "POSSIBLE",
  "medical": "VERY_UNLIKELY",
  "spoof": "VERY_UNLIKELY"
}
```

**Likelihood values:** `UNKNOWN`, `VERY_UNLIKELY`, `UNLIKELY`, `POSSIBLE`, `LIKELY`, `VERY_LIKELY`

---

## 🌍 Federation — ActivityPub

Implements the [ActivityPub](https://www.w3.org/TR/activitypub/) (W3C) and [WebFinger](https://tools.ietf.org/html/rfc7033) protocols for cross-instance interoperability.

### `GET /.well-known/webfinger`

WebFinger resource discovery. Remote servers query this to find actor URLs.

| Parameter | Type | Location | Description |
|---|---|---|---|
| `resource` | `string` | query | `acct:username@domain` format |

**Response:** WebFinger JRD document with links to the actor profile.

---

### `GET /users/{username}`

ActivityPub actor profile. Returns a JSON-LD document with the user's public key, inbox, outbox, and profile metadata.

| Parameter | Type | Location | Description |
|---|---|---|---|
| `username` | `string` | path | Local username |

**Response:** JSON-LD `Person` object with `@context`, `id`, `inbox`, `outbox`, `publicKey`, etc.

**Content-Type:** `application/activity+json`

---

### `POST /users/{username}/inbox`

Per-user inbox for receiving ActivityPub activities from remote instances. Delegates to shared inbox logic.

| Parameter | Type | Location | Description |
|---|---|---|---|
| `username` | `string` | path | Target local username |

---

### `POST /inbox`

Shared inbox for receiving federated activities.

**Supported Activity Types:**

| Activity | Description |
|---|---|
| `Create` | Incoming post from a remote user — saved locally with `is_remote=True` |
| `Delete` | Remove a remote post by its ActivityPub ID |
| `Follow` | Incoming follow request — auto-accepts and sends `Accept` activity |
| `Accept` | Confirmation that a remote server accepted our follow — marks connection as `"accepted"` and fetches outbox |
| `Undo` | Undo a previous activity (e.g., unfollow) |

---

### `GET /users/{username}/outbox`

ActivityPub outbox. Returns an `OrderedCollection` of the user's public posts. Supports pagination via the `page` query parameter.

| Parameter | Type | Location | Description |
|---|---|---|---|
| `username` | `string` | path | Local username |
| `page` | `bool` | query | If `true`, returns paginated `OrderedCollectionPage` with post items |

---

### `POST /sync-remote-posts`

Manually sync posts from all remote users the current user follows. Fetches their outbox and stores new posts locally.

🔒 **Requires authentication**

---

## 🔧 Utility / Debug Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/debug/timeline-state` | Debug: show raw DB state for connected-user timeline |
| `GET` | `/debug/connections` | Debug: view all connections and their statuses |
| `DELETE` | `/delete_remote/{id}` | Delete a specific remote post |
| `GET` | `/health/redis` | Check Redis connectivity and stats |

---

## Error Responses

All errors follow a consistent format:

```json
{
  "detail": "Error description"
}
```

Common HTTP status codes:

| Code | Meaning |
|---|---|
| `400` | Bad Request — invalid input |
| `401` | Unauthorized — missing or invalid token |
| `403` | Forbidden — insufficient permissions |
| `404` | Not Found — resource doesn't exist |
| `409` | Conflict — duplicate resource |
| `413` | Payload Too Large — file size exceeded |
| `500` | Internal Server Error |

---

<p align="center">
  <em>For interactive testing, visit the <a href="https://heliix.studio/docs">Swagger UI</a>.</em>
</p>
