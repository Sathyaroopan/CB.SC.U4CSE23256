# Campus Notifications Microservice - System Design

# Stage 1

Core actions: fetch notifications, mark as read, get unread count, create notification, real-time delivery.

Endpoints:

- GET /api/notifications?page=1&limit=20&type=Placement&is_read=false — fetch paginated notifications
- PATCH /api/notifications/read — body: { "notification_ids": ["uuid-1"] } — mark as read
- GET /api/notifications/unread-count — returns { "unread_count": 12 }
- POST /api/notifications — internal, creates notification for given student_ids
- GET /api/notifications/stream — SSE endpoint for real-time push

All endpoints require Authorization: Bearer <token> header.

Notifications have: id (UUID), type (Placement/Result/Event), message, timestamp, is_read.

Real-time mechanism: SSE (Server-Sent Events) — chosen over WebSocket because notifications are one-way (server to client), SSE auto-reconnects, and works with standard HTTP.

# Stage 2

Database: PostgreSQL — ACID compliant, supports composite/partial indexes, native enums, table partitioning.

Schema:

```sql
CREATE TYPE notification_type AS ENUM ('Placement', 'Result', 'Event');

CREATE TABLE students (
    id UUID PRIMARY KEY, email VARCHAR(255) UNIQUE, name VARCHAR(255), roll_no VARCHAR(50) UNIQUE
);

CREATE TABLE notifications (
    id UUID PRIMARY KEY, student_id UUID REFERENCES students(id),
    notification_type notification_type, message TEXT, is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_student_unread ON notifications (student_id, is_read, created_at DESC) WHERE is_read = FALSE;
```

Scaling: partition table by created_at monthly, use read replicas for GETs, PgBouncer for connection pooling, batch INSERT for broadcasts.

# Stage 3

Original query is slow because: no composite index (full 5M row scan), SELECT \* fetches unnecessary data, ORDER BY without index = in-memory sort, no pagination.

Fix: select only needed columns, add LIMIT, use composite partial index on (student_id, is_read, created_at DESC) WHERE is_read = FALSE.

Indexing every column is bad — slows writes, wastes storage, confuses query planner. Only index columns used in actual query WHERE/ORDER BY patterns.

Placement notifications in last 7 days:

```sql
SELECT DISTINCT s.id, s.name, s.email FROM students s
JOIN notifications n ON s.id = n.student_id
WHERE n.notification_type = Placement AND n.created_at >= NOW() - INTERVAL 7 days;
```

# Stage 4

Problem: DB overwhelmed by reads on every page load.

Solution: Redis cache-aside. Check Redis first, if miss then query DB and cache with 60s TTL. Invalidate on new notification or mark-as-read. Cache unread counts separately with 30s TTL.

Tradeoff: stale data for up to TTL seconds, but eliminates 90%+ DB read load.

# Stage 5

Original notify_all problems: sequential loop over 50K students is slow (~83 min at 100ms/email), no error isolation, no retry, email+DB coupled, no idempotency.

DB save and email should NOT happen together — DB is fast/reliable, email is slow/unreliable. Save to DB first (source of truth), then dispatch emails async via message queue.

Redesign: batch INSERT all notifications into DB first, then publish jobs to email_queue and push_queue. Workers process in parallel with retry (exponential backoff) and dead letter queue for permanent failures. Use batch_id for idempotency.

# Stage 6

Priority Inbox: show top N notifications ranked by type weight (Placement=3 > Result=2 > Event=1) then recency.

Data structure: min-heap of size N. O(n log N) total. Handles streaming new notifications efficiently — each insert/eviction is O(log N).

See notification_app_be/priority_inbox.py for implementation.
