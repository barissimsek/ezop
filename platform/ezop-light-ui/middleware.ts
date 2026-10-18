import { auth } from "@/auth"

export default auth((req) => {
  const isLoggedIn = !!req.auth
  const { pathname } = req.nextUrl

  if (!isLoggedIn && (pathname.startsWith("/dashboard") || pathname.startsWith("/onboarding") || pathname.startsWith("/subscription"))) {
    return Response.redirect(new URL("/", req.nextUrl))
  }
})

export const config = {
  matcher: ["/dashboard/:path*", "/onboarding", "/subscription"],
}
