import { NextResponse } from 'next/server'
// Kicks off the Google flow on the backend. The browser navigates here, then the
// backend redirects to Google, and eventually back to the frontend with a JWT.
const API = process.env.API_URL ?? 'http://localhost:3001'
export async function GET() {
  return NextResponse.redirect(`${API}/auth/google/login`)
}
