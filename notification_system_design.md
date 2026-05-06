# Campus Notifications Microservice - System Design

# Stage 1

A front-end developer needs to display notifications to logged-in students. The platform needs to support a few core actions: students should be able to fetch their notifications (with filtering by type and read status), mark them as read, and see how many unread notifications they have. On the backend side, internal services need a way to create new notifications. And since this is a real-time platform, students should see new notifications appear without refreshing the page.

Here's how I'd design the REST API:

- **GET /api/notifications** — The main endpoint. Accepts query parameters like page, limit, type (Placement, Result, or Event), and is_read. Returns a paginated list of notifications, each with an id, type, message, timestamp, and read status.
- **PATCH /api/notifications/read** — Accepts a list of notification IDs in the body and marks them as read.
- **GET /api/notifications/unread-count** — A lightweight endpoint that just returns the unread count, useful for showing a badge on the UI.
- **POST /api/notifications** — An internal endpoint that other services call to create notifications for a list of students.
- **GET /api/notifications/stream** — The real-time endpoint using Server-Sent Events (SSE).

Every endpoint requires a Bearer token in the Authorization header.

For real-time delivery, I chose SSE over WebSocket. Notifications are inherently one-way — the server pushes them to the client, the client doesn't need to send anything back. SSE is simpler (it's just HTTP), has built-in auto-reconnection, and works fine with standard load balancers. WebSocket would be overkill here.

# Stage 2

For persistent storage, I'd go with PostgreSQL. It gives us ACID compliance (important when tracking read/unread state), excellent indexing options including partial indexes, native enum types for our notification categories, and table partitioning when we need to scale.

The schema is straightforward — a students table and a notifications table linked by student_id:

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

As data grows, we'd partition the notifications table by month, add read replicas to offload GET queries, and use connection pooling (PgBouncer) to handle more concurrent connections. For mass broadcasts, batch INSERTs are far more efficient than inserting one row at a time.

# Stage 3

The original query fetches all unread notifications for a student:

```sql
SELECT * FROM notifications WHERE studentID = 1042 AND isRead = false ORDER BY createdAt DESC;
```

With fifty thousand students and five million notifications, this query would crawl. Without a composite index, the database has to scan the entire table to find matching rows. Using SELECT \* pulls back every column even if the UI only needs a few fields. The ORDER BY forces an in-memory sort since there's no index to guide it. And without any LIMIT, it could return thousands of rows in a single response.

The fix is to select only the columns we need, add pagination with LIMIT/OFFSET, and create a composite partial index on (student_id, is_read, created_at DESC) that only covers unread rows. This partial index is much smaller and faster than a full-table index.

A colleague suggested indexing every column "to be safe." That's actually counterproductive — every index slows down writes because the database has to update all of them on every INSERT and UPDATE. Indexes on low-cardinality columns (like is_read, which only has two possible values) provide almost no benefit to the query planner. The right approach is to create targeted indexes based on actual query patterns.

For finding students who received placement notifications in the last week:

```sql
SELECT DISTINCT s.id, s.name, s.email FROM students s
JOIN notifications n ON s.id = n.student_id
WHERE n.notification_type = Placement AND n.created_at >= NOW() - INTERVAL 7 days;
```

# Stage 4

The database is getting hammered because notifications are fetched on every single page load. The solution is to put a Redis cache in front of it.

The pattern is simple: when a student's notifications are requested, check Redis first. If we have a cached copy, return it immediately without touching the database. If not, query the database, cache the result with a short TTL (around a minute), and return it. Whenever a new notification arrives or something gets marked as read, we invalidate that student's cache so the next request gets fresh data.

Unread counts are especially worth caching separately since they're requested on every page navigation — a shorter TTL of about thirty seconds works well there.

The tradeoff is that data can be slightly stale (up to the TTL duration), but this eliminates the vast majority of database reads. For a notification system, a few seconds of staleness is perfectly acceptable.

# Stage 5

The original notify_all implementation loops sequentially through every student — sending an email, saving to the database, and pushing a real-time notification for each one. With fifty thousand students, this is painfully slow. If each email takes even a hundred milliseconds, the entire process would take over an hour. Worse, if the email API fails partway through, the remaining students never get notified. There's no retry logic, and if the process crashes and restarts, students might get duplicate notifications.

The email send and database save should not happen together. The database is local, fast, and reliable. The email API is external, slow, and can fail at any time. Coupling them means a flaky email service blocks everything.

The redesign separates concerns: first, do a single batch INSERT to save all notifications into the database (this is the source of truth and takes milliseconds). Then, publish individual email and push notification jobs to a message queue. A pool of workers picks up these jobs in parallel, with retry logic using exponential backoff — if an email fails, it gets retried after a few seconds, then longer delays, up to a maximum number of attempts. Jobs that permanently fail go to a dead letter queue for manual investigation. A batch ID ensures idempotency, so if the process restarts, we don't create duplicate notifications.

# Stage 6

User feedback suggests adding a Priority Inbox that shows the most important unread notifications first. Priority is based on the notification type — placements matter most, then results, then events — with more recent notifications ranking higher as a tiebreaker.

To efficiently maintain the top N notifications, I use a min-heap of size N. As each notification comes in, we compare its priority score against the weakest entry in the heap. If it's better, we swap them out. This runs in O(n log N) time and works well even when new notifications keep streaming in, since each insertion or eviction is just O(log N).

The implementation is in notification_app_be/priority_inbox.py.
