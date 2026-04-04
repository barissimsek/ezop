"use client"

import UserMenu from "@/components/UserMenu"

export default function UserMenuWrapper({
  name,
  signOutAction,
}: {
  name: string | null | undefined
  signOutAction: () => Promise<void>
}) {
  return <UserMenu name={name} onSignOut={() => signOutAction()} />
}
