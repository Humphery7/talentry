# Talentry (Next.js 15, App Router, TypeScript)
    npm install && npm run dev      # http://localhost:3000
- `lib/data.ts`: mock DB + query logic (replace with Prisma/Drizzle). `lib/api.ts` is the seam server pages call.
- `app/api/*`: GET /api/jobs, GET /api/jobs/:id, POST /api/applications.
- Filters live in the URL (`/jobs?loc=Remote&types=Contract`). Saved jobs use localStorage until you add auth (`lib/useSaved.ts`).
- Set `NEXT_PUBLIC_API_URL` to call an external backend from client components.
