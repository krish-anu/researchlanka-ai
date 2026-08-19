import { redirect } from "next/navigation";

import { signUp } from "@/app/actions/auth";
import { AuthForm } from "@/components/auth/AuthForm";
import { RoleBadge } from "@/components/auth/RoleBadge";
import { ROLE_CAPABILITY_SUMMARY } from "@/services/auth/permissions";
import { getViewer } from "@/services/auth/server";
import { ROLE_DESCRIPTION } from "@/types/auth";

export const metadata = {
  title: "Create an account",
  description:
    "Create a ResearchLanka account to save publications and flag records for review.",
};

interface PageProps {
  searchParams: Promise<{ next?: string }>;
}

function safeNext(value: string | undefined): string {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return "/";
  return value;
}

export default async function RegisterPage({ searchParams }: PageProps) {
  const { next } = await searchParams;
  const destination = safeNext(next);

  if ((await getViewer()).user) redirect(destination);

  return (
    <div className="mx-auto grid w-full max-w-4xl gap-8 md:grid-cols-[minmax(0,1fr)_18rem]">
      <div className="panel p-6 md:p-8">
        <h1 className="title-page text-ink">Create an account</h1>
        <p className="mt-2 max-w-prose text-body-sm text-ink-secondary">
          New accounts are created as signed-in users. Administrator access is
          granted by an existing administrator — it cannot be claimed here.
        </p>
        <div className="mt-6">
          <AuthForm action={signUp} mode="sign-up" next={destination} />
        </div>
      </div>

      <aside className="panel h-fit p-5">
        <RoleBadge role="user" />
        <p className="mt-3 text-body-sm text-ink-secondary">
          {ROLE_DESCRIPTION.user}
        </p>
        <ul className="mt-3 flex flex-col gap-2 border-t border-rule pt-3 text-body-sm text-ink-secondary">
          {ROLE_CAPABILITY_SUMMARY.user.map((line) => (
            <li key={line} className="flex gap-2">
              <span aria-hidden className="text-muted">
                ·
              </span>
              {line}
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}
