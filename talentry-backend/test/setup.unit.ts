// Unit tests never touch a database. The pool connects lazily, so a dummy URL is
// enough, and overriding it here guarantees the real .env URL is never used.
process.env.DATABASE_URL = 'postgresql://unused:unused@localhost:5432/unused';
process.env.JWT_SECRET = 'test-secret';
