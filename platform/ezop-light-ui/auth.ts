import NextAuth from "next-auth"
import Google from "next-auth/providers/google"
import Credentials from "next-auth/providers/credentials"

export const { handlers, auth, signIn, signOut } = NextAuth({
  trustHost: true,
  providers: [
    Google({
      clientId: process.env.GOOGLE_CLIENT_ID,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET,
      authorization: {
        params: { prompt: "select_account" },
      },
    }),
    // Test-only: never active in production (AUTH_TEST_SECRET is not set there)
    ...(process.env.AUTH_TEST_SECRET
      ? [
          Credentials({
            credentials: { secret: { type: "password" } },
            async authorize({ secret }) {
              if (secret !== process.env.AUTH_TEST_SECRET) return null
              return {
                id: "aaaaaaaa-0000-0000-0000-000000000001",
                name: "Test User",
                email: "playwright@test.example.com",
              }
            },
          }),
        ]
      : []),
  ],
})
