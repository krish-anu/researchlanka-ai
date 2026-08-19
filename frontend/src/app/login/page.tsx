import Link from "next/link";
import { redirect } from "next/navigation";

import { signIn } from "@/app/actions/auth";
import { AuthForm } from "@/components/auth/AuthForm";
import { getViewer } from "@/services/auth/server";
import { ROLE_CAPABILITY_SUMMARY } from "@/services/auth/permissions";

export const metadata = {
  title: "Sign in",
  description:
    "Sign in to save publications to a library and flag records for review.",
};

interface PageProps {
  searchParams: Promise<{ next?: string }>;
}

/** Never bounce someone off-site after sign-in; see `safeNext` in the action. */
function safeNext(value: string | undefined): string {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return "/";
  return value;
}

export default async function LoginPage({ searchParams }: PageProps) {
  const { next } = await searchParams;
  const destination = safeNext(next);

  // Already signed in — the form would be a dead end.
  if ((await getViewer()).user) redirect(destination);

  return (
    <div className="mx-auto grid w-full max-w-4xl gap-8 md:grid-cols-[minmax(0,1fr)_18rem]">
      <div className="panel p-6 md:p-8">
        <h1 className="title-page text-ink">Sign in</h1>
        <p className="mt-2 max-w-prose text-body-sm text-ink-secondary">
          The corpus, dashboards and exports stay open to everyone. An account
          adds a saved library and lets you flag records that look wrong.
        </p>
        <div className="mt-6">
          <AuthForm action={signIn} mode="sign-in" next={destination} />
        </div>
      </div>

      <aside className="panel h-fit p-5">
        <h2 className="label-caps text-muted">Without an account</h2>
        <ul className="mt-3 flex flex-col gap-2 text-body-sm text-ink-secondary">
          {ROLE_CAPABILITY_SUMMARY.guest.map((line) => (
            <li key={line} className="flex gap-2">
              <span aria-hidden className="text-muted">
                ·
              </span>
              {line}
            </li>
          ))}
        </ul>
        <Link
          href="/"
          className="mt-4 inline-block text-body-sm text-primary underline"
        >
          Continue as a visitor
        </Link>
      </aside>
    </div>
  );
}
